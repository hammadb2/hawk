-- HAWK Pulse Engine (PR #54) — Core tables for event-driven CTEM
-- Supabase Migration

-- Enable UUID extension (already enabled by default on Supabase, but safe to call)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Monitored Domains
CREATE TABLE IF NOT EXISTS monitored_domains (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain      VARCHAR(255) NOT NULL UNIQUE,
    owner_email VARCHAR(255),
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_monitored_domains_domain
    ON monitored_domains (domain);

-- 2. Assets (discovered subdomains, ports, certs, HTTP services)
CREATE TABLE IF NOT EXISTS assets (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_id   UUID NOT NULL REFERENCES monitored_domains(id) ON DELETE CASCADE,
    asset_type  VARCHAR(50) NOT NULL,   -- subdomain | open_port | certificate | http_service
    asset_key   VARCHAR(512) NOT NULL,  -- e.g. 'api.example.com:443' or cert fingerprint
    metadata    JSONB NOT NULL DEFAULT '{}',
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_new      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_assets_domain_type_key
    ON assets (domain_id, asset_type, asset_key);

-- 3. Alerts (state-change events)
CREATE TABLE IF NOT EXISTS alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_id       UUID NOT NULL REFERENCES monitored_domains(id) ON DELETE CASCADE,
    alert_type      VARCHAR(50) NOT NULL,   -- new_asset | asset_gone | cert_issued | port_opened | port_closed
    severity        VARCHAR(20) NOT NULL DEFAULT 'info',
    title           VARCHAR(512) NOT NULL,
    detail          JSONB NOT NULL DEFAULT '{}',
    asset_id        UUID REFERENCES assets(id),
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_alerts_domain_created
    ON alerts (domain_id, created_at);

-- 4. Scan Events (audit log)
CREATE TABLE IF NOT EXISTS scan_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_id       UUID NOT NULL REFERENCES monitored_domains(id) ON DELETE CASCADE,
    trigger         VARCHAR(50) NOT NULL,   -- certstream | scheduled | manual
    trigger_detail  JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    result_summary  JSONB NOT NULL DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);
