-- 2B prep — attack path chaining (Claude) stored per scan; UI in roadmap
alter table public.crm_prospect_scans
  add column if not exists attack_paths jsonb not null default '[]'::jsonb;

comment on column public.crm_prospect_scans.attack_paths is 'Top attack paths narrative (2B); JSON array of {name, steps, likelihood, impact}';
