-- P3 — Readiness score, guarantee status, SLA tracking, audit events

alter table public.clients
  add column if not exists hawk_readiness_score integer not null default 100
    check (hawk_readiness_score >= 0 and hawk_readiness_score <= 100),
  add column if not exists guarantee_status text not null default 'active'
    check (guarantee_status in ('active', 'at_risk', 'suspended')),
  add column if not exists guarantee_checklist_critical_ok boolean not null default true,
  add column if not exists guarantee_checklist_high_ok boolean not null default true,
  add column if not exists guarantee_checklist_subscription_ok boolean not null default true,
  add column if not exists certified_at timestamptz;

comment on column public.clients.hawk_readiness_score is '0–100 after SLA penalties; updated after each Shield rescan';
comment on column public.clients.guarantee_status is 'active | at_risk | suspended from score thresholds';
comment on column public.clients.certified_at is 'Set when HAWK Certified earned (90-day track); portal Earned state';

-- Per-finding SLA clocks for penalties + 20h/24h critical alerts
create table if not exists public.hawk_finding_sla (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  finding_key text not null,
  severity text not null,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  cleared_at timestamptz,
  alert_20h_sent_at timestamptz,
  alert_24h_sent_at timestamptz,
  created_at timestamptz not null default now(),
  unique (client_id, finding_key)
);

create index if not exists idx_hawk_finding_sla_client_open
  on public.hawk_finding_sla (client_id)
  where cleared_at is null;

alter table public.hawk_finding_sla enable row level security;

create table if not exists public.hawk_guarantee_events (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  old_status text,
  new_status text,
  readiness_score integer,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_hawk_guarantee_events_client
  on public.hawk_guarantee_events (client_id, created_at desc);

alter table public.hawk_guarantee_events enable row level security;

-- Portal: read own guarantee events (optional audit in UI)
drop policy if exists "hawk_guarantee_events_select_portal" on public.hawk_guarantee_events;
create policy "hawk_guarantee_events_select_portal"
  on public.hawk_guarantee_events for select
  to authenticated
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = hawk_guarantee_events.client_id
        and cpp.user_id = auth.uid()
    )
  );

-- Service role / backend uses service key (bypasses RLS)
