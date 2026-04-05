-- Phase 4 — Enterprise multi-domain scans, attacker simulation reports, RLS

-- Extra monitored domains (primary remains clients.domain); max 4 extras = 5 total with primary
alter table public.clients
  add column if not exists monitored_domains text[] not null default '{}'::text[];

alter table public.clients
  drop constraint if exists clients_monitored_domains_max;

alter table public.clients
  add constraint clients_monitored_domains_max
  check (cardinality(monitored_domains) <= 4);

comment on column public.clients.monitored_domains is 'Additional apex domains to scan (max 4); primary domain is clients.domain';

-- Latest scan snapshot per client × domain (enterprise rollup)
create table if not exists public.client_domain_scans (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  domain text not null,
  hawk_score int,
  grade text,
  findings jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_client_domain_scans_client_domain_time
  on public.client_domain_scans (client_id, domain, created_at desc);

-- Weekly Claude “attacker simulation” narrative for portal
create table if not exists public.client_attacker_simulation_reports (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  week_start date not null,
  title text,
  body_md text not null,
  created_at timestamptz not null default now(),
  unique (client_id, week_start)
);

create index if not exists idx_attacker_sim_client_week
  on public.client_attacker_simulation_reports (client_id, week_start desc);

alter table public.client_domain_scans enable row level security;
alter table public.client_attacker_simulation_reports enable row level security;

drop policy if exists "client_domain_scans_portal_select" on public.client_domain_scans;
create policy "client_domain_scans_portal_select"
  on public.client_domain_scans for select to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = client_domain_scans.client_id and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "client_attacker_sim_portal_select" on public.client_attacker_simulation_reports;
create policy "client_attacker_sim_portal_select"
  on public.client_attacker_simulation_reports for select to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = client_attacker_simulation_reports.client_id and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "client_domain_scans_ceo_select" on public.client_domain_scans;
create policy "client_domain_scans_ceo_select"
  on public.client_domain_scans for select
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role in ('ceo', 'hos'))
  );

drop policy if exists "client_attacker_sim_ceo_select" on public.client_attacker_simulation_reports;
create policy "client_attacker_sim_ceo_select"
  on public.client_attacker_simulation_reports for select
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role in ('ceo', 'hos'))
  );
