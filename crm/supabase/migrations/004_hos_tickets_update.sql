-- HoS can triage tickets (was read-only via hos_tickets_read only)
CREATE POLICY "hos_tickets_update" ON tickets
  FOR UPDATE TO authenticated
  USING (get_my_role() = 'hos')
  WITH CHECK (get_my_role() = 'hos');
