-- HAWK Guard — AI Remediation Engine (PR #55)
-- Adds remediation columns to the alerts table
-- Supabase Migration

ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS remediation_markdown TEXT,
    ADD COLUMN IF NOT EXISTS remediation_status   VARCHAR(20);

COMMENT ON COLUMN alerts.remediation_markdown IS 'AI-generated fix guide (Markdown)';
COMMENT ON COLUMN alerts.remediation_status   IS 'pending | generating | complete | failed';
