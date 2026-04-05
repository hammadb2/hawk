-- Phase 2 — Make It Sticky: remediation tracking, threat briefings, milestones, competitor benchmark metadata

-- ---------------------------------------------------------------------------
-- Per-finding workflow status (portal)
-- ---------------------------------------------------------------------------
create table if not exists public.portal_finding_status (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  scan_id uuid not null,
  finding_id text not null,
  status text not null default 'open'
    check (status in ('open', 'in_progress', 'fixed', 'accepted_risk')),
  updated_at timestamptz not null default now(),
  verified_at timestamptz,
  verify_error text,
  unique (client_id, finding_id)
);

create index if not exists idx_portal_finding_status_client on public.portal_finding_status (client_id);

comment on table public.portal_finding_status is 'Portal remediation workflow; finding_id matches crm_prospect_scans.findings JSON ids';

-- ---------------------------------------------------------------------------
-- Weekly AI threat briefing (generated + emailed)
-- ---------------------------------------------------------------------------
create table if not exists public.client_threat_briefings (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  week_start date not null,
  title text,
  body_md text not null,
  industry_snapshot text,
  email_sent_at timestamptz,
  created_at timestamptz not null default now(),
  unique (client_id, week_start)
);

create index if not exists idx_client_threat_briefings_client_week
  on public.client_threat_briefings (client_id, week_start desc);

-- ---------------------------------------------------------------------------
-- Gamification milestones
-- ---------------------------------------------------------------------------
create table if not exists public.client_security_milestones (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  milestone_key text not null,
  achieved_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  unique (client_id, milestone_key)
);

create index if not exists idx_client_security_milestones_client on public.client_security_milestones (client_id);

-- ---------------------------------------------------------------------------
-- Competitor / industry benchmark (scores + narrative; competitor scans = later)
-- ---------------------------------------------------------------------------
create table if not exists public.client_competitor_benchmarks (
  client_id uuid primary key references public.clients (id) on delete cascade,
  competitor_domains text[] not null default '{}',
  scores jsonb not null default '{}'::jsonb,
  narrative_md text,
  refreshed_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.portal_finding_status enable row level security;
alter table public.client_threat_briefings enable row level security;
alter table public.client_security_milestones enable row level security;
alter table public.client_competitor_benchmarks enable row level security;

drop policy if exists "portal_finding_status_select" on public.portal_finding_status;
create policy "portal_finding_status_select"
  on public.portal_finding_status for select to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = portal_finding_status.client_id and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "portal_finding_status_insert" on public.portal_finding_status;
create policy "portal_finding_status_insert"
  on public.portal_finding_status for insert to authenticated
  with check (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = portal_finding_status.client_id and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "portal_finding_status_update" on public.portal_finding_status;
create policy "portal_finding_status_update"
  on public.portal_finding_status for update to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = portal_finding_status.client_id and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "client_threat_briefings_select" on public.client_threat_briefings;
create policy "client_threat_briefings_select"
  on public.client_threat_briefings for select to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = client_threat_briefings.client_id and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "client_security_milestones_select" on public.client_security_milestones;
create policy "client_security_milestones_select"
  on public.client_security_milestones for select to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = client_security_milestones.client_id and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "client_competitor_benchmarks_select" on public.client_competitor_benchmarks;
create policy "client_competitor_benchmarks_select"
  on public.client_competitor_benchmarks for select to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = client_competitor_benchmarks.client_id and cpp.user_id = auth.uid()
    )
  );
