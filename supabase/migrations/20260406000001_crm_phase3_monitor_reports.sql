-- Phase 3 — Self-healing monitor log, monthly report audit, Realtime on activities (CEO feed)

-- ---------------------------------------------------------------------------
-- system_health_log — monitor cron writes via service role; CEO reads in app
-- ---------------------------------------------------------------------------
create table if not exists public.system_health_log (
  id uuid primary key default gen_random_uuid(),
  service text not null,
  status text not null check (status in ('ok', 'degraded', 'failed')),
  response_ms int,
  checked_at timestamptz not null default now(),
  detail jsonb not null default '{}'::jsonb,
  alert_sent boolean not null default false
);

create index if not exists idx_system_health_log_service_checked on public.system_health_log (service, checked_at desc);

alter table public.system_health_log enable row level security;

drop policy if exists "system_health_log_select_ceo" on public.system_health_log;
create policy "system_health_log_select_ceo"
  on public.system_health_log for select
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'ceo')
  );

-- ---------------------------------------------------------------------------
-- Monthly PDF deliveries (audit trail for Phase 3C)
-- ---------------------------------------------------------------------------
create table if not exists public.crm_monthly_report_log (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  month_year text not null,
  storage_path text,
  sent_to_email text,
  status text not null default 'sent' check (status in ('pending', 'sent', 'failed')),
  created_at timestamptz not null default now(),
  unique (client_id, month_year)
);

create index if not exists idx_crm_monthly_report_log_month on public.crm_monthly_report_log (month_year desc);

alter table public.crm_monthly_report_log enable row level security;

drop policy if exists "crm_monthly_report_log_select_ceo" on public.crm_monthly_report_log;
create policy "crm_monthly_report_log_select_ceo"
  on public.crm_monthly_report_log for select
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role in ('ceo', 'hos'))
  );

-- ---------------------------------------------------------------------------
-- Realtime: activities for CEO live feed (idempotent)
-- ---------------------------------------------------------------------------
do $realtime$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'activities'
  ) then
    alter publication supabase_realtime add table public.activities;
  end if;
end;
$realtime$;
