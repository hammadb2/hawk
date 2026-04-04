-- Homepage scanner leads: source value + optional top_finding on prospects

alter table public.prospects
  add column if not exists top_finding text;

alter table public.prospects drop constraint if exists prospects_source_check;
alter table public.prospects add constraint prospects_source_check
  check (source in ('charlotte', 'manual', 'inbound', 'homepage_scanner'));
