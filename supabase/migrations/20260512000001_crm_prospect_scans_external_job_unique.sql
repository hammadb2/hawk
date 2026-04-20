-- Add partial UNIQUE index on crm_prospect_scans.external_job_id so the
-- Postgrest `Prefer: resolution=merge-duplicates` header actually dedupes
-- the inserts we make from the SLA auto-scanner (and the frontend finalize
-- route). Without this, duplicate rows could accumulate if the same scan
-- job gets processed twice (e.g. watchdog releases a slow job that then
-- completes alongside a retry).
--
-- Uses WHERE external_job_id IS NOT NULL so older pre-scanner-v2 rows (and
-- any manual DB inserts without a job id) can still coexist without
-- violating the constraint.

CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_prospect_scans_external_job_id
  ON public.crm_prospect_scans (external_job_id)
  WHERE external_job_id IS NOT NULL;
