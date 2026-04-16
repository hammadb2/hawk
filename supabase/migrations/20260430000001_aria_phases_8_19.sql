-- ARIA Phases 8-19: Additional tables for voice, A/B testing, competitive intel,
-- playbooks, WhatsApp, API keys, webhooks, and training sessions.

-- ── Phase 10: A/B Experiments ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_ab_experiments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    variant_a jsonb NOT NULL DEFAULT '{}'::jsonb,
    variant_b jsonb NOT NULL DEFAULT '{}'::jsonb,
    campaign_id text,
    status text NOT NULL DEFAULT 'created',
    results jsonb,
    winner text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_ab_experiments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_ab_experiments"
    ON aria_ab_experiments FOR ALL
    USING (auth.role() = 'service_role');

-- ── Phase 11: Competitive Intelligence ────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_competitive_intel (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type text NOT NULL DEFAULT 'competitive_analysis',
    content jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_competitive_intel ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_competitive_intel"
    ON aria_competitive_intel FOR ALL
    USING (auth.role() = 'service_role');

-- ── Phase 14: Playbooks ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_playbooks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    content jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_playbooks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_playbooks"
    ON aria_playbooks FOR ALL
    USING (auth.role() = 'service_role');

-- ── Phase 17: API Keys ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    key_hash text NOT NULL UNIQUE,
    permissions jsonb NOT NULL DEFAULT '{}'::jsonb,
    rate_limit int NOT NULL DEFAULT 100,
    active boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES profiles(id),
    last_used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_api_keys"
    ON aria_api_keys FOR ALL
    USING (auth.role() = 'service_role');

-- ── Phase 17: Webhooks ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_webhooks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    url text NOT NULL,
    events jsonb NOT NULL DEFAULT '[]'::jsonb,
    signing_secret text,
    api_key_id uuid REFERENCES aria_api_keys(id) ON DELETE CASCADE,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_webhooks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_webhooks"
    ON aria_webhooks FOR ALL
    USING (auth.role() = 'service_role');

-- ── Phase 18: WhatsApp Messages ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_whatsapp_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    direction text NOT NULL,  -- 'inbound' or 'outbound'
    phone text NOT NULL,
    content text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_whatsapp_messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_whatsapp_messages"
    ON aria_whatsapp_messages FOR ALL
    USING (auth.role() = 'service_role');

CREATE TABLE IF NOT EXISTS aria_whatsapp_queue (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phone text NOT NULL,
    inbound_text text NOT NULL DEFAULT '',
    drafted_reply text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'pending',  -- pending, sent, rejected, failed
    sent_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_whatsapp_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_whatsapp_queue"
    ON aria_whatsapp_queue FOR ALL
    USING (auth.role() = 'service_role');

-- ── Phase 19: Training Sessions ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_training_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES profiles(id),
    scenario_type text NOT NULL,
    title text NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'active',  -- active, completed
    messages jsonb NOT NULL DEFAULT '[]'::jsonb,
    score int,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_training_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on aria_training_sessions"
    ON aria_training_sessions FOR ALL
    USING (auth.role() = 'service_role');

-- ── Indices ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_aria_ab_experiments_status ON aria_ab_experiments(status);
CREATE INDEX IF NOT EXISTS idx_aria_competitive_intel_created ON aria_competitive_intel(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aria_api_keys_hash ON aria_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_aria_webhooks_api_key ON aria_webhooks(api_key_id);
CREATE INDEX IF NOT EXISTS idx_aria_whatsapp_messages_phone ON aria_whatsapp_messages(phone);
CREATE INDEX IF NOT EXISTS idx_aria_whatsapp_queue_status ON aria_whatsapp_queue(status);
CREATE INDEX IF NOT EXISTS idx_aria_training_sessions_user ON aria_training_sessions(user_id);
