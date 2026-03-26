-- ─── HAWK CRM Row Level Security Policies ─────────────────────────────────────
-- Run after schema.sql

-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE prospects ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE commissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppressions ENABLE ROW LEVEL SECURITY;

-- ─── users table ───────────────────────────────────────────────────────────────

-- CEO sees all users
CREATE POLICY "ceo_all_users" ON users
  FOR ALL USING (get_my_role() = 'ceo');

-- HoS sees all users
CREATE POLICY "hos_all_users" ON users
  FOR SELECT USING (get_my_role() = 'hos');

-- Team Lead sees own profile + their reps
CREATE POLICY "team_lead_users" ON users
  FOR SELECT USING (
    get_my_role() = 'team_lead'
    AND (id = auth.uid() OR team_lead_id = auth.uid())
  );

-- Rep sees own profile only
CREATE POLICY "rep_own_user" ON users
  FOR SELECT USING (get_my_role() = 'rep' AND id = auth.uid());

-- Any authenticated user can update their own profile
CREATE POLICY "own_profile_update" ON users
  FOR UPDATE USING (id = auth.uid());

-- ─── prospects table ───────────────────────────────────────────────────────────

-- CEO and HoS see all prospects
CREATE POLICY "ceo_hos_all_prospects" ON prospects
  FOR ALL USING (get_my_role() IN ('ceo', 'hos'));

-- Team Lead sees own team's prospects
CREATE POLICY "team_lead_prospects" ON prospects
  FOR ALL USING (
    get_my_role() = 'team_lead'
    AND assigned_rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid() OR id = auth.uid())
  );

-- Rep sees only their own prospects
CREATE POLICY "rep_own_prospects" ON prospects
  FOR ALL USING (
    get_my_role() = 'rep'
    AND assigned_rep_id = auth.uid()
  );

-- ─── clients table ─────────────────────────────────────────────────────────────

-- CEO and HoS see all clients
CREATE POLICY "ceo_hos_all_clients" ON clients
  FOR ALL USING (get_my_role() IN ('ceo', 'hos'));

-- Team Lead sees team clients
CREATE POLICY "team_lead_clients" ON clients
  FOR SELECT USING (
    get_my_role() = 'team_lead'
    AND closing_rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid() OR id = auth.uid())
  );

-- Rep sees own closed clients
CREATE POLICY "rep_own_clients" ON clients
  FOR SELECT USING (
    get_my_role() = 'rep'
    AND (closing_rep_id = auth.uid() OR csm_rep_id = auth.uid())
  );

-- ─── activities table ──────────────────────────────────────────────────────────

-- CEO and HoS see all activities
CREATE POLICY "ceo_hos_all_activities" ON activities
  FOR ALL USING (get_my_role() IN ('ceo', 'hos'));

-- Team Lead sees own team's activities
CREATE POLICY "team_lead_activities" ON activities
  FOR SELECT USING (
    get_my_role() = 'team_lead'
    AND (
      created_by IN (SELECT id FROM users WHERE team_lead_id = auth.uid() OR id = auth.uid())
      OR prospect_id IN (SELECT id FROM prospects WHERE assigned_rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid() OR id = auth.uid()))
    )
  );

-- Rep sees activities on their prospects/clients
CREATE POLICY "rep_own_activities" ON activities
  FOR SELECT USING (
    get_my_role() = 'rep'
    AND (
      created_by = auth.uid()
      OR prospect_id IN (SELECT id FROM prospects WHERE assigned_rep_id = auth.uid())
      OR client_id IN (SELECT id FROM clients WHERE closing_rep_id = auth.uid() OR csm_rep_id = auth.uid())
    )
  );

-- Any authenticated user can create activities on their own prospects
CREATE POLICY "create_own_activity" ON activities
  FOR INSERT WITH CHECK (created_by = auth.uid());

-- ─── email_events table ────────────────────────────────────────────────────────

-- CEO and HoS see all email events
CREATE POLICY "ceo_hos_all_email_events" ON email_events
  FOR ALL USING (get_my_role() IN ('ceo', 'hos'));

-- Team Lead sees team email events
CREATE POLICY "team_lead_email_events" ON email_events
  FOR SELECT USING (
    get_my_role() = 'team_lead'
    AND prospect_id IN (
      SELECT id FROM prospects
      WHERE assigned_rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid() OR id = auth.uid())
    )
  );

-- Rep sees email events for their prospects
CREATE POLICY "rep_own_email_events" ON email_events
  FOR SELECT USING (
    get_my_role() = 'rep'
    AND prospect_id IN (SELECT id FROM prospects WHERE assigned_rep_id = auth.uid())
  );

-- ─── crm_scans table ───────────────────────────────────────────────────────────

-- CEO and HoS see all scans
CREATE POLICY "ceo_hos_all_scans" ON crm_scans
  FOR ALL USING (get_my_role() IN ('ceo', 'hos'));

-- Team Lead sees team scans
CREATE POLICY "team_lead_scans" ON crm_scans
  FOR SELECT USING (
    get_my_role() = 'team_lead'
    AND (
      prospect_id IN (SELECT id FROM prospects WHERE assigned_rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid() OR id = auth.uid()))
      OR triggered_by IN (SELECT id FROM users WHERE team_lead_id = auth.uid() OR id = auth.uid())
    )
  );

-- Rep sees scans on their prospects
CREATE POLICY "rep_own_scans" ON crm_scans
  FOR SELECT USING (
    get_my_role() = 'rep'
    AND (
      prospect_id IN (SELECT id FROM prospects WHERE assigned_rep_id = auth.uid())
      OR triggered_by = auth.uid()
    )
  );

-- Rep can create scans
CREATE POLICY "rep_create_scan" ON crm_scans
  FOR INSERT WITH CHECK (triggered_by = auth.uid());

-- ─── commissions table ─────────────────────────────────────────────────────────

-- CEO and HoS see all commissions
CREATE POLICY "ceo_hos_all_commissions" ON commissions
  FOR ALL USING (get_my_role() IN ('ceo', 'hos'));

-- Team Lead sees their own + team overrides
CREATE POLICY "team_lead_commissions" ON commissions
  FOR SELECT USING (
    get_my_role() = 'team_lead'
    AND (
      rep_id = auth.uid()
      OR rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid())
    )
  );

-- Rep sees only own commissions
CREATE POLICY "rep_own_commissions" ON commissions
  FOR SELECT USING (
    get_my_role() = 'rep'
    AND rep_id = auth.uid()
  );

-- ─── tickets table ─────────────────────────────────────────────────────────────

-- CEO sees all tickets
CREATE POLICY "ceo_all_tickets" ON tickets
  FOR ALL USING (get_my_role() = 'ceo');

-- HoS sees all tickets (read-only)
CREATE POLICY "hos_tickets_read" ON tickets
  FOR SELECT USING (get_my_role() = 'hos');

-- All authenticated users can submit tickets
CREATE POLICY "submit_own_ticket" ON tickets
  FOR INSERT WITH CHECK (submitted_by = auth.uid());

-- Users can read their own tickets
CREATE POLICY "own_tickets_read" ON tickets
  FOR SELECT USING (submitted_by = auth.uid());

-- ─── audit_log table ───────────────────────────────────────────────────────────

-- CEO only can read audit log
CREATE POLICY "ceo_audit_log" ON audit_log
  FOR SELECT USING (get_my_role() = 'ceo');

-- Allow inserts from service role (backend) only
-- Note: actual inserts happen via service role, not client-side

-- ─── suppressions table ────────────────────────────────────────────────────────

-- CEO and HoS manage suppressions
CREATE POLICY "ceo_hos_suppressions" ON suppressions
  FOR ALL USING (get_my_role() IN ('ceo', 'hos'));

-- All authenticated users can read suppressions (for validation)
CREATE POLICY "all_read_suppressions" ON suppressions
  FOR SELECT USING (auth.uid() IS NOT NULL);
