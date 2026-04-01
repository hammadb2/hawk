-- 2A — Daily Shield monitoring: snapshots for diffing + alert audit trail

create table if not exists public.client_shield_monitor_snapshots (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  domain text not null,
  scanned_at timestamptz not null default now(),
  hawk_score int,
  grade text,
  finding_keys text[] not null default '{}',
  detail jsonb not null default '{}'::jsonb
);

create index if not exists idx_shield_snapshots_client_time
  on public.client_shield_monitor_snapshots (client_id, scanned_at desc);

create table if not exists public.client_shield_monitor_events (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  created_at timestamptz not null default now(),
  channel text not null check (channel in ('whatsapp', 'email', 'both', 'none')),
  summary text not null,
  new_finding_keys text[] not null default '{}',
  detail jsonb not null default '{}'::jsonb
);

create index if not exists idx_shield_events_client_time
  on public.client_shield_monitor_events (client_id, created_at desc);

alter table public.client_shield_monitor_snapshots enable row level security;
alter table public.client_shield_monitor_events enable row level security;

-- CEO / HoS read-only (service role bypasses for cron)
drop policy if exists "shield_snapshots_select_privileged" on public.client_shield_monitor_snapshots;
create policy "shield_snapshots_select_privileged"
  on public.client_shield_monitor_snapshots for select
  using (
    exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role in ('ceo', 'hos'))
  );

drop policy if exists "shield_events_select_privileged" on public.client_shield_monitor_events;
create policy "shield_events_select_privileged"
  on public.client_shield_monitor_events for select
  using (
    exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role in ('ceo', 'hos'))
  );
