-- ============================================================
-- Migration 002: Section 20 Data Bridge
-- Run after schema.sql and rls.sql
-- ============================================================

-- ── Extend clients table ─────────────────────────────────────
ALTER TABLE clients
  ADD COLUMN IF NOT EXISTS hawk_user_id        text,          -- links to HAWK product users.id
  ADD COLUMN IF NOT EXISTS csm_rep_id          uuid REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS churn_risk_numeric  int DEFAULT 0, -- 0–100
  ADD COLUMN IF NOT EXISTS renewal_date        timestamptz,
  ADD COLUMN IF NOT EXISTS trial_end_date      timestamptz,
  ADD COLUMN IF NOT EXISTS seat_count          int DEFAULT 1,
  ADD COLUMN IF NOT EXISTS billing_status      text DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS nps_latest          int,
  ADD COLUMN IF NOT EXISTS nps_comment         text,
  ADD COLUMN IF NOT EXISTS nps_at              timestamptz;

-- Extend churn_risk_score to include 'critical'
ALTER TABLE clients
  DROP CONSTRAINT IF EXISTS clients_churn_risk_score_check;
ALTER TABLE clients
  ADD CONSTRAINT clients_churn_risk_score_check
    CHECK (churn_risk_score IN ('low','medium','high','critical'));

-- Add CSM role to users
ALTER TABLE users
  DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users
  ADD CONSTRAINT users_role_check
    CHECK (role IN ('ceo','hos','team_lead','rep','csm','charlotte'));

-- ── client_health_sync ───────────────────────────────────────
-- Snapshot of HAWK product state per client, written by sync job
CREATE TABLE IF NOT EXISTS client_health_sync (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id                 uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  hawk_user_id              text NOT NULL,

  -- Account identity
  account_owner_name        text,
  account_owner_email       text,
  company_name              text,
  plan                      text,
  trial_start_date          timestamptz,
  trial_end_date            timestamptz,
  subscription_start_date   timestamptz,
  renewal_date              timestamptz,
  billing_status            text,
  mrr                       numeric(10,2),
  seat_count                int DEFAULT 1,
  primary_domain            text,
  all_domains               jsonb DEFAULT '[]',

  -- Product usage
  total_scans               int DEFAULT 0,
  scans_this_month          int DEFAULT 0,
  last_scan_date            timestamptz,
  features_accessed         jsonb DEFAULT '{}',   -- {feature_name: true/false}
  reports_generated         int DEFAULT 0,
  reports_downloaded        int DEFAULT 0,
  compliance_accessed       boolean DEFAULT false,
  agency_accessed           boolean DEFAULT false,
  sessions_this_month       int DEFAULT 0,
  last_login_date           timestamptz,
  avg_session_minutes       numeric(6,2),
  onboarding_pct            int DEFAULT 0,        -- 0–100
  onboarding_steps_done     jsonb DEFAULT '[]',

  -- Health signals
  nps_score                 int,
  nps_comment               text,
  nps_submitted_at          timestamptz,
  tickets_open              int DEFAULT 0,
  tickets_closed_month      int DEFAULT 0,
  cancellation_intent       boolean DEFAULT false,
  cancellation_intent_at    timestamptz,
  downgrade_requested       boolean DEFAULT false,
  upgrade_clicked           boolean DEFAULT false,
  payment_failed_count      int DEFAULT 0,

  -- Calculated
  churn_risk_numeric        int DEFAULT 0,        -- 0–100
  churn_risk_label          text DEFAULT 'low',   -- low/medium/high/critical

  synced_at                 timestamptz NOT NULL DEFAULT now(),
  created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_client_health_sync_client_id ON client_health_sync(client_id);
CREATE INDEX IF NOT EXISTS idx_client_health_sync_hawk_user_id ON client_health_sync(hawk_user_id);

-- ── onboarding_tasks ─────────────────────────────────────────
-- Auto-generated CSM task sequence for new paid clients
CREATE TABLE IF NOT EXISTS onboarding_tasks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id     uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  csm_rep_id    uuid REFERENCES users(id),
  day_number    int NOT NULL,                      -- 0, 1, 3, 7, 14, 30
  title         text NOT NULL,
  description   text,
  due_date      timestamptz NOT NULL,
  status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','completed','skipped','overdue')),
  completed_at  timestamptz,
  completed_by  uuid REFERENCES users(id),
  notes         text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_onboarding_tasks_client_id ON onboarding_tasks(client_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_tasks_csm_rep_id ON onboarding_tasks(csm_rep_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_tasks_due_date ON onboarding_tasks(due_date);

-- ── trial_nurture_log ────────────────────────────────────────
-- Tracks which behaviour-triggered nurture actions have fired per prospect
CREATE TABLE IF NOT EXISTS trial_nurture_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prospect_id   uuid REFERENCES prospects(id) ON DELETE CASCADE,
  hawk_user_id  text,
  trigger_type  text NOT NULL,   -- never_scanned_day1, ran_scan_no_upgrade_day2, viewed_pricing, day7_features, day12_rep_task, day14_expiry, expired_no_convert
  fired_at      timestamptz NOT NULL DEFAULT now(),
  metadata      jsonb DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trial_nurture_log_prospect_id ON trial_nurture_log(prospect_id);
CREATE INDEX IF NOT EXISTS idx_trial_nurture_log_hawk_user_id ON trial_nurture_log(hawk_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trial_nurture_log_unique
  ON trial_nurture_log(hawk_user_id, trigger_type);

-- ── RLS for new tables ───────────────────────────────────────

ALTER TABLE client_health_sync ENABLE ROW LEVEL SECURITY;
ALTER TABLE onboarding_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE trial_nurture_log ENABLE ROW LEVEL SECURITY;

-- client_health_sync: readable by anyone who can see the client
CREATE POLICY "client_health_sync_select" ON client_health_sync
  FOR SELECT USING (
    get_my_role() IN ('ceo','hos')
    OR EXISTS (
      SELECT 1 FROM clients c
      WHERE c.id = client_id
        AND (c.closing_rep_id = auth.uid() OR c.csm_rep_id = auth.uid())
    )
  );

-- Only service role (backend) writes health sync
CREATE POLICY "client_health_sync_insert_service" ON client_health_sync
  FOR INSERT WITH CHECK (get_my_role() IN ('ceo','hos'));

-- onboarding_tasks: CSM sees their own, HoS/CEO see all
CREATE POLICY "onboarding_tasks_select" ON onboarding_tasks
  FOR SELECT USING (
    get_my_role() IN ('ceo','hos')
    OR csm_rep_id = auth.uid()
  );

CREATE POLICY "onboarding_tasks_update" ON onboarding_tasks
  FOR UPDATE USING (
    get_my_role() IN ('ceo','hos')
    OR csm_rep_id = auth.uid()
  );

-- trial_nurture_log: HoS/CEO/Charlotte see all, rep sees own prospects
CREATE POLICY "trial_nurture_log_select" ON trial_nurture_log
  FOR SELECT USING (
    get_my_role() IN ('ceo','hos','charlotte')
    OR EXISTS (
      SELECT 1 FROM prospects p
      WHERE p.id = prospect_id AND p.assigned_rep_id = auth.uid()
    )
  );
