-- Repair: some environments have public.clients without company_name (or related columns)
-- from pre-phase1 drafts. App + RLS expect the phase1 shape from 20260329000001_crm_phase1_core.sql.

alter table public.clients add column if not exists company_name text;
alter table public.clients add column if not exists domain text;
alter table public.clients add column if not exists plan text;
