-- Phase 3 — Email event metadata, dedupe key, source

alter table public.prospect_email_events
  add column if not exists source text not null default 'webhook',
  add column if not exists external_id text,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

comment on column public.prospect_email_events.source is 'smartlead | charlotte | webhook | manual';
comment on column public.prospect_email_events.external_id is 'Provider id for idempotent ingest (unique per prospect when set)';

create unique index if not exists idx_prospect_email_events_external_dedupe
  on public.prospect_email_events (prospect_id, external_id)
  where external_id is not null and length(trim(external_id)) > 0;
