-- ─── HAWK CRM Schema ───────────────────────────────────────────────────────────
-- Run in Supabase SQL editor to initialize the database.

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name text NOT NULL,
  email text NOT NULL UNIQUE,
  role text NOT NULL CHECK (role IN ('ceo','hos','team_lead','rep')),
  team_lead_id uuid REFERENCES users(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','at_risk','inactive')),
  last_close_at timestamptz,
  whatsapp_number text,
  invited_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz DEFAULT now()
);

-- ─── prospects ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prospects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  domain text NOT NULL,
  company_name text NOT NULL,
  industry text,
  city text,
  province text,
  stage text NOT NULL DEFAULT 'new' CHECK (stage IN ('new','scanned','loom_sent','replied','call_booked','proposal_sent','closed_won','lost')),
  assigned_rep_id uuid REFERENCES users(id) ON DELETE SET NULL,
  hawk_score integer CHECK (hawk_score BETWEEN 0 AND 100),
  source text NOT NULL DEFAULT 'manual' CHECK (source IN ('charlotte','manual','inbound','referral')),
  consent_basis text DEFAULT 'implied',
  is_hot boolean DEFAULT false,
  duplicate_of uuid REFERENCES prospects(id) ON DELETE SET NULL,
  lost_reason text,
  lost_notes text,
  reactivate_at timestamptz,
  apollo_data jsonb,
  created_at timestamptz DEFAULT now(),
  last_activity_at timestamptz DEFAULT now()
);

-- ─── clients ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prospect_id uuid REFERENCES prospects(id) ON DELETE SET NULL,
  plan text NOT NULL CHECK (plan IN ('starter','shield','enterprise','custom')),
  mrr numeric NOT NULL DEFAULT 0,
  stripe_customer_id text,
  stripe_subscription_id text,
  closing_rep_id uuid REFERENCES users(id) ON DELETE SET NULL,
  csm_rep_id uuid REFERENCES users(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','past_due','churned')),
  close_date timestamptz DEFAULT now(),
  clawback_deadline timestamptz,
  churn_risk_score text DEFAULT 'low' CHECK (churn_risk_score IN ('low','medium','high')),
  nps_latest integer CHECK (nps_latest BETWEEN 0 AND 10),
  last_login_at timestamptz,
  created_at timestamptz DEFAULT now()
);

-- ─── activities ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prospect_id uuid REFERENCES prospects(id) ON DELETE CASCADE,
  client_id uuid REFERENCES clients(id) ON DELETE CASCADE,
  type text NOT NULL CHECK (type IN ('call','email_sent','stage_changed','scan_run','note_added','loom_sent','task_created','task_completed','hot_flagged','reassigned','close_won')),
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  notes text,
  metadata jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

-- ─── email_events ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS email_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prospect_id uuid REFERENCES prospects(id) ON DELETE CASCADE,
  smartlead_event_type text NOT NULL,
  subject text,
  sequence_step integer,
  sent_at timestamptz,
  opened_at timestamptz,
  open_count integer DEFAULT 0,
  clicked_at timestamptz,
  click_count integer DEFAULT 0,
  replied_at timestamptz,
  reply_sentiment text CHECK (reply_sentiment IN ('positive','negative','question','ooo')),
  created_at timestamptz DEFAULT now()
);

-- ─── crm_scans ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_scans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prospect_id uuid REFERENCES prospects(id) ON DELETE CASCADE,
  client_id uuid REFERENCES clients(id) ON DELETE CASCADE,
  hawk_score integer CHECK (hawk_score BETWEEN 0 AND 100),
  findings jsonb DEFAULT '[]',
  triggered_by uuid REFERENCES users(id) ON DELETE SET NULL,
  status text DEFAULT 'pending' CHECK (status IN ('pending','complete','failed')),
  created_at timestamptz DEFAULT now()
);

-- ─── commissions ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS commissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  type text NOT NULL CHECK (type IN ('closing','residual','bonus','override','clawback')),
  amount numeric NOT NULL DEFAULT 0,
  client_id uuid REFERENCES clients(id) ON DELETE SET NULL,
  month_year text NOT NULL, -- format: "2026-03"
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','paid','clawback')),
  deel_payment_ref text,
  calculated_at timestamptz DEFAULT now()
);

-- ─── tickets ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submitted_by uuid REFERENCES users(id) ON DELETE SET NULL,
  channel text NOT NULL CHECK (channel IN ('in_crm','whatsapp','email','auto_detected')),
  raw_text text NOT NULL,
  classification text,
  severity integer CHECK (severity BETWEEN 1 AND 5),
  status text NOT NULL DEFAULT 'received' CHECK (status IN ('received','in_progress','resolved','duplicate','monitoring')),
  triage_diagnosis text,
  pr_url text,
  resolved_at timestamptz,
  resolution_type text,
  parent_ticket_id uuid REFERENCES tickets(id) ON DELETE SET NULL,
  created_at timestamptz DEFAULT now()
);

-- ─── audit_log ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  action text NOT NULL,
  record_type text NOT NULL,
  record_id uuid,
  old_value jsonb,
  new_value jsonb,
  ip_address text,
  created_at timestamptz DEFAULT now()
);

-- audit_log is immutable — prevent updates and deletes
CREATE OR REPLACE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE OR REPLACE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- ─── suppressions ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suppressions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  domain text,
  email text,
  reason text NOT NULL CHECK (reason IN ('unsubscribe','bounce','manual')),
  added_at timestamptz DEFAULT now(),
  added_by uuid REFERENCES users(id) ON DELETE SET NULL
);

-- ─── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_prospects_assigned_rep ON prospects(assigned_rep_id);
CREATE INDEX IF NOT EXISTS idx_prospects_stage ON prospects(stage);
CREATE INDEX IF NOT EXISTS idx_prospects_last_activity ON prospects(last_activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_activities_prospect ON activities(prospect_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activities_client ON activities(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_events_prospect ON email_events(prospect_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commissions_rep ON commissions(rep_id, month_year);
CREATE INDEX IF NOT EXISTS idx_commissions_month ON commissions(month_year);
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_clients_churn ON clients(churn_risk_score);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_suppressions_domain ON suppressions(domain);
CREATE INDEX IF NOT EXISTS idx_suppressions_email ON suppressions(email);

-- ─── Functions ─────────────────────────────────────────────────────────────────

-- Function to get current user's role
CREATE OR REPLACE FUNCTION get_my_role()
RETURNS text
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
  SELECT role FROM users WHERE id = auth.uid();
$$;

-- Function to get current user's team_lead_id
CREATE OR REPLACE FUNCTION get_my_team_lead_id()
RETURNS uuid
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
  SELECT team_lead_id FROM users WHERE id = auth.uid();
$$;

-- Function to get rep IDs under a team lead
CREATE OR REPLACE FUNCTION get_team_rep_ids(lead_id uuid)
RETURNS SETOF uuid
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
  SELECT id FROM users WHERE team_lead_id = lead_id;
$$;

-- Trigger to update last_activity_at on activity insert
CREATE OR REPLACE FUNCTION update_prospect_last_activity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.prospect_id IS NOT NULL THEN
    UPDATE prospects SET last_activity_at = NEW.created_at WHERE id = NEW.prospect_id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_update_prospect_last_activity
AFTER INSERT ON activities
FOR EACH ROW EXECUTE FUNCTION update_prospect_last_activity();
