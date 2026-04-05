-- Phase 3 — Daily dnstwist monitoring: store registered permutation set per Shield client for diffing

create table if not exists public.client_dnstwist_snapshots (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  domain text not null,
  registered_domains text[] not null default '{}',
  fingerprint text not null,
  raw_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_dnstwist_snapshots_client_time
  on public.client_dnstwist_snapshots (client_id, created_at desc);

create index if not exists idx_dnstwist_snapshots_domain
  on public.client_dnstwist_snapshots (domain);

alter table public.client_dnstwist_snapshots enable row level security;

drop policy if exists "dnstwist_snapshots_ceo_select" on public.client_dnstwist_snapshots;
create policy "dnstwist_snapshots_ceo_select"
  on public.client_dnstwist_snapshots for select
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.role in ('ceo', 'hos')
    )
  );
