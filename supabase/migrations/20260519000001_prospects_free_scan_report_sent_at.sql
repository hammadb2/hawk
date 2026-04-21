-- Free-scan landing page (securedbyhawk.com/free-scan) — inbound lead capture
-- with a "3-finding report within 24 hours" promise. We need a dedicated
-- timestamp so the dispatch cron (`/api/crm/cron/free-scan-dispatch-reports`)
-- knows which free-scan prospects have already been sent their report and
-- which are still owed one.
--
-- Nullable + idempotent. No backfill required — legacy prospects that never
-- went through the free-scan funnel stay NULL and are ignored by the cron.

alter table public.prospects
  add column if not exists free_scan_report_sent_at timestamptz;

comment on column public.prospects.free_scan_report_sent_at is
  'UTC timestamp the 3-finding report email was delivered to a free-scan '
  'landing page lead (source=free_scan_landing). NULL = not sent yet. '
  'Used by /api/crm/cron/free-scan-dispatch-reports to pick work.';

-- Partial index powering the dispatch cron — only free-scan leads that have
-- completed a scan but haven't been mailed yet.
create index if not exists idx_prospects_free_scan_pending
  on public.prospects (scanned_at)
  where source = 'free_scan_landing'
    and scanned_at is not null
    and free_scan_report_sent_at is null;
