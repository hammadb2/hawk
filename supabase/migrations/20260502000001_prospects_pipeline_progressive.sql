-- Progressive ARIA pipeline visibility on CRM prospects (no drops of existing columns)

alter table public.prospects
  add column if not exists address text,
  add column if not exists province text,
  add column if not exists pipeline_status text,
  add column if not exists email_finder text,
  add column if not exists zero_bounce_result text,
  add column if not exists vulnerability_found text,
  add column if not exists vulnerability_type text,
  add column if not exists email_subject text,
  add column if not exists email_body text,
  add column if not exists smartlead_campaign_id text,
  add column if not exists dispatched_at timestamptz,
  add column if not exists lead_score integer,
  add column if not exists google_rating double precision,
  add column if not exists review_count integer,
  add column if not exists pipeline_run_id uuid references public.aria_pipeline_runs (id) on delete set null;

comment on column public.prospects.pipeline_status is 'ARIA outbound pipeline stage: discovered, enriched, verified, scanned, ready, contacted, suppressed';

alter table public.prospects drop constraint if exists prospects_source_check;
alter table public.prospects add constraint prospects_source_check
  check (source in (
    'charlotte',
    'manual',
    'inbound',
    'homepage_scanner',
    'aria_nightly',
    'aria_chat'
  ));

create index if not exists idx_prospects_pipeline_status
  on public.prospects (pipeline_status)
  where pipeline_status is not null;

create index if not exists idx_prospects_pipeline_run
  on public.prospects (pipeline_run_id)
  where pipeline_run_id is not null;
