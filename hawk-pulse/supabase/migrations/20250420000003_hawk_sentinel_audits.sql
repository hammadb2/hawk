-- HAWK Sentinel — AI Red Team (PR #56 / Step 3)
-- Creates the sentinel_audits table for tracking penetration test audits
-- Supabase Migration

CREATE TABLE IF NOT EXISTS sentinel_audits (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_id       UUID NOT NULL REFERENCES monitored_domains(id) ON DELETE CASCADE,
    status          VARCHAR(30) NOT NULL DEFAULT 'roe_pending',
    scope_json      JSONB NOT NULL DEFAULT '{}',
    roe_chat_history JSONB NOT NULL DEFAULT '[]',
    container_id    VARCHAR(80),
    agent_log       JSONB NOT NULL DEFAULT '[]',
    findings        JSONB NOT NULL DEFAULT '[]',
    report_markdown TEXT,
    report_url      VARCHAR(1024),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for querying audits by domain and status
CREATE INDEX IF NOT EXISTS ix_sentinel_audits_domain_status
    ON sentinel_audits (domain_id, status);

-- Add comments
COMMENT ON TABLE sentinel_audits IS 'HAWK Sentinel penetration test audits';
COMMENT ON COLUMN sentinel_audits.status IS 'roe_pending | roe_agreed | provisioning | scanning | reporting | complete | failed';
COMMENT ON COLUMN sentinel_audits.scope_json IS 'Rules of Engagement contract (scope.json)';
COMMENT ON COLUMN sentinel_audits.roe_chat_history IS 'Full ROE negotiation chat history';
COMMENT ON COLUMN sentinel_audits.container_id IS 'Docker container ID for the Kali sandbox';
COMMENT ON COLUMN sentinel_audits.agent_log IS 'Agent execution log (planner, ghost, operator, cleanup)';
COMMENT ON COLUMN sentinel_audits.findings IS 'Penetration test findings from the operator agent';
COMMENT ON COLUMN sentinel_audits.report_markdown IS 'Final CISO report in Markdown';
COMMENT ON COLUMN sentinel_audits.report_url IS 'URL/path to the generated PDF report';
