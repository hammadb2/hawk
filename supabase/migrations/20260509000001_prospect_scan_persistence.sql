-- Persistent async scan state + SLA auto-scan support.
--
-- Problem: the manual "Run scan" button on /crm/prospects/[id] keeps progress
-- in React state only; page reload drops it. Also: any prospect sitting in
-- `stage=new` for longer than 10 minutes should be auto-scanned by the
-- scheduler and either progressed (`stage=scanned`) or soft-dropped
-- (`stage=lost` + suppressions row) if its hawk_score is ≥ 85.
--
-- This migration adds the state columns used by both flows. Idempotent.

alter table public.prospects
  add column if not exists active_scan_job_id text,
  add column if not exists scan_started_at timestamptz,
  add column if not exists scan_last_polled_at timestamptz,
  add column if not exists scan_trigger text,          -- 'manual' | 'sla_auto' | 'nightly'
  add column if not exists scanned_at timestamptz;

-- If a prior draft of this migration created active_scan_job_id as uuid
-- (scanner job ids are opaque strings, not guaranteed UUID), coerce it to text
-- so PostgREST writes from the SLA job + /api/crm/run-scan never fail.
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'prospects'
      and column_name = 'active_scan_job_id'
      and data_type = 'uuid'
  ) then
    execute 'alter table public.prospects alter column active_scan_job_id type text using active_scan_job_id::text';
  end if;
end$$;

comment on column public.prospects.active_scan_job_id is
  'Job id returned by hawk-scanner-v2 /v1/scan/async while a scan is in flight. Cleared on completion, failure, or timeout. Drives the persistent scanning-state UI.';
comment on column public.prospects.scan_started_at is
  'UTC timestamp when the current scan was enqueued. Used to compute watchdog timeout (~10 min) in case the worker crashes mid-scan.';
comment on column public.prospects.scan_trigger is
  'Who started the in-flight scan: manual (user clicked Run scan), sla_auto (stage=new > 10 min), nightly (aria pipeline).';
comment on column public.prospects.scanned_at is
  'UTC timestamp of the last successful scan result write. Used by the SLA auto-scan job so we don''t re-scan the same prospect repeatedly.';

create index if not exists idx_prospects_active_scan_job_id
  on public.prospects (active_scan_job_id)
  where active_scan_job_id is not null;

-- Partial index used by the every-2-min SLA auto-scan job to find prospects
-- stuck in stage=new with no active scan.
create index if not exists idx_prospects_stage_new_no_scan
  on public.prospects (created_at)
  where stage = 'new' and active_scan_job_id is null and scanned_at is null;
