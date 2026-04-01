-- Phase 2 — Client portal accounts, onboarding sequences, portal RLS

-- ---------------------------------------------------------------------------
-- clients: portal link + sequence tracking
-- ---------------------------------------------------------------------------
alter table public.clients
  add column if not exists portal_user_id uuid references auth.users (id) on delete set null,
  add column if not exists onboarding_sequence_status text not null default 'pending'
    check (onboarding_sequence_status in ('pending', 'in_progress', 'completed', 'paused')),
  add column if not exists last_portal_login_at timestamptz;

create index if not exists idx_clients_portal_user on public.clients (portal_user_id);

-- ---------------------------------------------------------------------------
-- Portal identity (1:1 auth user ↔ CRM client)
-- ---------------------------------------------------------------------------
create table if not exists public.client_portal_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  client_id uuid not null references public.clients (id) on delete cascade,
  email text not null,
  company_name text,
  domain text,
  created_at timestamptz not null default now(),
  unique (user_id),
  unique (client_id)
);

create index if not exists idx_client_portal_profiles_client on public.client_portal_profiles (client_id);

-- ---------------------------------------------------------------------------
-- Drip / onboarding emails (Phase 2B)
-- ---------------------------------------------------------------------------
create table if not exists public.client_onboarding_sequences (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  step text not null,
  status text not null default 'pending' check (status in ('pending', 'sent', 'skipped', 'failed')),
  sent_at timestamptz,
  opened_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_client_onboarding_sequences_client on public.client_onboarding_sequences (client_id, step);
create index if not exists idx_client_onboarding_sequences_pending
  on public.client_onboarding_sequences (status, created_at)
  where status = 'pending';

-- ---------------------------------------------------------------------------
-- Trigger: skip CRM profiles row for client-portal-only auth users
-- ---------------------------------------------------------------------------
create or replace function public.crm_handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  initial_status text;
  wa text;
  tl uuid;
  portal_cid text;
begin
  portal_cid := nullif(trim(coalesce(new.raw_user_meta_data->>'portal_client_id', '')), '');
  if portal_cid is not null and portal_cid <> '' then
    return new;
  end if;

  initial_status := nullif(trim(lower(coalesce(new.raw_user_meta_data->>'crm_initial_status', ''))), '');
  wa := nullif(trim(coalesce(new.raw_user_meta_data->>'whatsapp_number', '')), '');
  begin
    tl := (new.raw_user_meta_data->>'crm_team_lead_id')::uuid;
  exception when others then
    tl := null;
  end;

  insert into public.profiles (id, email, full_name, role, status, whatsapp_number, team_lead_id)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
    coalesce(new.raw_user_meta_data->>'crm_role', 'sales_rep'),
    case
      when initial_status in ('invited', 'onboarding') then initial_status
      else 'active'
    end,
    wa,
    tl
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = coalesce(excluded.full_name, public.profiles.full_name);
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.client_portal_profiles enable row level security;
alter table public.client_onboarding_sequences enable row level security;

drop policy if exists "client_portal_profiles_select_own" on public.client_portal_profiles;
create policy "client_portal_profiles_select_own"
  on public.client_portal_profiles for select
  using (user_id = auth.uid());

drop policy if exists "client_onboarding_sequences_select_portal" on public.client_onboarding_sequences;
create policy "client_onboarding_sequences_select_portal"
  on public.client_onboarding_sequences for select
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = client_onboarding_sequences.client_id
        and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "clients_select_portal" on public.clients;
create policy "clients_select_portal"
  on public.clients for select
  using (
    exists (
      select 1 from public.client_portal_profiles cpp
      where cpp.client_id = clients.id
        and cpp.user_id = auth.uid()
    )
  );

drop policy if exists "prospects_select_portal" on public.prospects;
create policy "prospects_select_portal"
  on public.prospects for select
  using (
    exists (
      select 1
      from public.client_portal_profiles cpp
      join public.clients c on c.id = cpp.client_id
      where cpp.user_id = auth.uid()
        and c.prospect_id = prospects.id
    )
  );

drop policy if exists "crm_prospect_scans_select_portal" on public.crm_prospect_scans;
create policy "crm_prospect_scans_select_portal"
  on public.crm_prospect_scans for select
  using (
    exists (
      select 1
      from public.client_portal_profiles cpp
      join public.clients c on c.id = cpp.client_id
      where cpp.user_id = auth.uid()
        and c.prospect_id = crm_prospect_scans.prospect_id
    )
  );

-- CEO profile anchor
insert into public.profiles (id, email, full_name, role, status, created_at)
values (
  'f04140d6-5f9c-4d93-94b9-5df24555496b',
  'hammadmkac@gmail.com',
  'Hammad Bhatti',
  'ceo',
  'active',
  now()
)
on conflict (id) do update set
  role = 'ceo',
  status = 'active',
  full_name = 'Hammad Bhatti';
