-- Guardian client risk — events from browser extension + server-built profiles (CEO/HoS only via RLS).

-- Optional phone for SMS alerts (extension / guardian flows).
alter table public.clients add column if not exists contact_phone text;

-- ---------------------------------------------------------------------------
-- client_guardian_profiles — one row per client; built by API profiler.
-- ---------------------------------------------------------------------------
create table if not exists public.client_guardian_profiles (
  client_id uuid primary key references public.clients (id) on delete cascade,
  domain text,
  known_login_urls text[] not null default '{}',
  trusted_sender_domains text[] not null default '{}',
  safe_browsing_status text not null default 'unknown'
    check (safe_browsing_status in ('clean', 'threat', 'unknown', 'error')),
  domain_whois_created_at timestamptz,
  bec_risk_score int not null default 0 check (bec_risk_score >= 0 and bec_risk_score <= 100),
  lookalike_flags jsonb not null default '[]'::jsonb,
  openai_warnings jsonb not null default '[]'::jsonb,
  last_profiled_at timestamptz,
  updated_at timestamptz not null default now()
);

create index if not exists idx_client_guardian_profiles_domain on public.client_guardian_profiles (domain);

-- ---------------------------------------------------------------------------
-- guardian_events — append-only security signals (extension + API).
-- ---------------------------------------------------------------------------
create table if not exists public.guardian_events (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  event_type text not null,
  severity text not null default 'medium'
    check (severity in ('info', 'low', 'medium', 'high', 'critical')),
  details jsonb not null default '{}'::jsonb,
  source text not null default 'extension' check (source in ('extension', 'api')),
  page_url text,
  created_at timestamptz not null default now()
);

create index if not exists idx_guardian_events_client_created on public.guardian_events (client_id, created_at desc);
create index if not exists idx_guardian_events_created on public.guardian_events (created_at desc);

-- ---------------------------------------------------------------------------
-- RLS — CEO/HoS read only (crm_is_privileged). No policies for clients role.
-- Service role bypasses RLS for inserts/updates from Railway API.
-- ---------------------------------------------------------------------------
alter table public.client_guardian_profiles enable row level security;
alter table public.guardian_events enable row level security;

drop policy if exists "client_guardian_profiles_select_privileged" on public.client_guardian_profiles;
create policy "client_guardian_profiles_select_privileged"
  on public.client_guardian_profiles for select
  using (public.crm_is_privileged());

drop policy if exists "guardian_events_select_privileged" on public.guardian_events;
create policy "guardian_events_select_privileged"
  on public.guardian_events for select
  using (public.crm_is_privileged());
