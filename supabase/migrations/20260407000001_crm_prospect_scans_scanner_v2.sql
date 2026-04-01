-- HAWK Scanner 2.0 — extended prospect scan payload (Railway pipeline + scoring)

alter table public.crm_prospect_scans
  add column if not exists scan_version text default '1.0',
  add column if not exists industry text,
  add column if not exists raw_layers jsonb not null default '{}'::jsonb,
  add column if not exists interpreted_findings jsonb not null default '[]'::jsonb,
  add column if not exists breach_cost_estimate jsonb not null default '{}'::jsonb,
  add column if not exists external_job_id text;

comment on column public.crm_prospect_scans.scan_version is 'Scanner release, e.g. 2.0';
comment on column public.crm_prospect_scans.industry is 'Industry label for risk multiplier (dental, medical, legal, financial, etc.)';
comment on column public.crm_prospect_scans.raw_layers is 'Per-layer tool output (subfinder, naabu, httpx, nuclei, …)';
comment on column public.crm_prospect_scans.interpreted_findings is 'Claude interpretations with fix guides per finding';
comment on column public.crm_prospect_scans.breach_cost_estimate is 'IBM-style sector breach cost context + inputs used';
comment on column public.crm_prospect_scans.external_job_id is 'Queue job id on Railway scanner worker';
