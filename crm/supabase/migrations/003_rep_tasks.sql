-- Rep follow-up tasks (spec: Today's task list on rep dashboard)
CREATE TABLE IF NOT EXISTS rep_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  prospect_id uuid REFERENCES prospects(id) ON DELETE SET NULL,
  title text NOT NULL,
  due_at timestamptz NOT NULL,
  completed_at timestamptz,
  notes text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rep_tasks_rep_due ON rep_tasks(rep_id, due_at);
CREATE INDEX IF NOT EXISTS idx_rep_tasks_open ON rep_tasks(rep_id) WHERE completed_at IS NULL;

ALTER TABLE rep_tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "rep_tasks_ceo" ON rep_tasks
  FOR ALL TO authenticated
  USING (get_my_role() = 'ceo')
  WITH CHECK (get_my_role() = 'ceo');

CREATE POLICY "rep_tasks_hos" ON rep_tasks
  FOR ALL TO authenticated
  USING (get_my_role() = 'hos')
  WITH CHECK (get_my_role() = 'hos');

CREATE POLICY "rep_tasks_team_lead" ON rep_tasks
  FOR ALL TO authenticated
  USING (
    get_my_role() = 'team_lead'
    AND (
      rep_id = auth.uid()
      OR rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid())
    )
  )
  WITH CHECK (
    get_my_role() = 'team_lead'
    AND (
      rep_id = auth.uid()
      OR rep_id IN (SELECT id FROM users WHERE team_lead_id = auth.uid())
    )
  );

CREATE POLICY "rep_tasks_rep" ON rep_tasks
  FOR ALL TO authenticated
  USING (get_my_role() = 'rep' AND rep_id = auth.uid())
  WITH CHECK (get_my_role() = 'rep' AND rep_id = auth.uid());
