-- Fix prospects.pipeline_status CHECK (20260515000001 listed wrong stages).
-- Code + SLA + dispatch use: discovered, enriched, verified, suppressed, scanned,
-- ready, contacted, dispatched, va_queue.
--
-- Remove legacy Apify toggle rows that 20260515000001 missed (wrong key names
-- in DELETE); real orphans: apify_enable_leadsfinder / linkedin / website_crawler.

update public.prospects
set pipeline_status = 'scanned'
where pipeline_status = 'scanning';

update public.prospects
set pipeline_status = 'enriched'
where pipeline_status = 'enriching';

update public.prospects
set pipeline_status = 'contacted'
where pipeline_status = 'closed';

alter table public.prospects drop constraint if exists prospects_pipeline_status_check;

alter table public.prospects
  add constraint prospects_pipeline_status_check
  check (
    pipeline_status is null
    or pipeline_status in (
      'discovered',
      'enriched',
      'verified',
      'suppressed',
      'scanned',
      'ready',
      'contacted',
      'dispatched',
      'va_queue'
    )
  );

comment on column public.prospects.pipeline_status is
  'ARIA outbound pipeline: discovered, enriched, verified, suppressed, scanned, ready, contacted, dispatched, va_queue';

-- Legacy per-actor keys (superseded by Apollo); 20260515000001 deleted wrong names.
delete from public.crm_settings
where key in (
  'apify_enable_leadsfinder',
  'apify_enable_linkedin',
  'apify_enable_website_crawler'
);
