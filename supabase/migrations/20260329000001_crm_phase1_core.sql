-- HAWK CRM Phase 1 — core tables + RLS (run in Supabase SQL editor or via CLI)

-- Extensions
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Profiles (1:1 with auth.users)
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  full_name text,
  role text not null default 'sales_rep'
    check (role in ('ceo', 'hos', 'team_lead', 'sales_rep')),
  team_lead_id uuid references public.profiles (id),
  avatar_url text,
  whatsapp_number text,
  status text not null default 'active' check (status in ('active', 'at_risk', 'inactive')),
  last_close_at timestamptz,
  monthly_close_target int default 10,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_profiles_team_lead on public.profiles (team_lead_id);
create index if not exists idx_profiles_role on public.profiles (role);

-- ---------------------------------------------------------------------------
-- Prospects
-- ---------------------------------------------------------------------------
create table if not exists public.prospects (
  id uuid primary key default gen_random_uuid(),
  domain text not null,
  company_name text,
  industry text,
  city text,
  stage text not null default 'new'
    check (stage in (
      'new', 'scanned', 'loom_sent', 'replied', 'call_booked',
      'proposal_sent', 'closed_won', 'lost'
    )),
  assigned_rep_id uuid references public.profiles (id),
  hawk_score int not null default 0 check (hawk_score >= 0 and hawk_score <= 100),
  source text not null default 'manual' check (source in ('charlotte', 'manual', 'inbound')),
  created_at timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  is_hot boolean not null default false,
  duplicate_of uuid references public.prospects (id),
  lost_reason text,
  lost_notes text,
  reactivate_on date,
  consent_basis text default 'implied_published_email',
  unique (domain)
);

create index if not exists idx_prospects_assigned on public.prospects (assigned_rep_id);
create index if not exists idx_prospects_stage on public.prospects (stage);
create index if not exists idx_prospects_created on public.prospects (created_at desc);

-- ---------------------------------------------------------------------------
-- Clients (minimal for Close Won in Phase 1)
-- ---------------------------------------------------------------------------
create table if not exists public.clients (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid references public.prospects (id),
  company_name text,
  domain text,
  plan text,
  mrr_cents int not null default 0,
  stripe_customer_id text,
  closing_rep_id uuid references public.profiles (id),
  status text not null default 'active' check (status in ('active', 'past_due', 'churned')),
  close_date timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists idx_clients_closing_rep on public.clients (closing_rep_id);

-- ---------------------------------------------------------------------------
-- Activities (timeline / feed)
-- ---------------------------------------------------------------------------
create table if not exists public.activities (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid references public.prospects (id) on delete cascade,
  client_id uuid references public.clients (id) on delete set null,
  type text not null,
  created_by uuid references public.profiles (id),
  notes text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_activities_prospect on public.activities (prospect_id);
create index if not exists idx_activities_created on public.activities (created_at desc);

-- ---------------------------------------------------------------------------
-- Notifications (in-app bell)
-- ---------------------------------------------------------------------------
create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  title text not null,
  message text not null,
  type text not null default 'info' check (type in ('info', 'success', 'warning', 'error')),
  read boolean not null default false,
  link text,
  created_at timestamptz not null default now()
);

create index if not exists idx_notifications_user_unread on public.notifications (user_id, read);

-- ---------------------------------------------------------------------------
-- Suppressions (Charlotte / CASL — referenced in later phases)
-- ---------------------------------------------------------------------------
create table if not exists public.suppressions (
  id uuid primary key default gen_random_uuid(),
  domain text,
  email text,
  reason text not null check (reason in ('unsubscribe', 'bounce', 'manual')),
  added_at timestamptz not null default now(),
  added_by uuid references public.profiles (id),
  constraint suppressions_domain_or_email check (domain is not null or email is not null)
);

-- ---------------------------------------------------------------------------
-- Audit log (append-only; Phase 1 schema — service role writes from API later)
-- ---------------------------------------------------------------------------
create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (id),
  action text not null,
  record_type text not null,
  record_id uuid,
  old_value jsonb,
  new_value jsonb,
  ip_address text,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Helper functions for RLS
-- ---------------------------------------------------------------------------
create or replace function public.crm_is_privileged()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select p.role in ('ceo', 'hos') from public.profiles p where p.id = auth.uid()),
    false
  );
$$;

create or replace function public.crm_is_team_member(rep uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select p.team_lead_id = auth.uid() from public.profiles p where p.id = rep),
    false
  );
$$;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.prospects enable row level security;
alter table public.clients enable row level security;
alter table public.activities enable row level security;
alter table public.notifications enable row level security;
alter table public.suppressions enable row level security;
alter table public.audit_log enable row level security;

-- Profiles
drop policy if exists "profiles_select_own_or_privileged" on public.profiles;
create policy "profiles_select_own_or_privileged"
  on public.profiles for select
  using (
    id = auth.uid()
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = auth.uid() and me.role = 'team_lead' and public.profiles.team_lead_id = me.id
    )
  );

drop policy if exists "profiles_update_self" on public.profiles;
create policy "profiles_update_self"
  on public.profiles for update
  using (id = auth.uid())
  with check (id = auth.uid());

drop policy if exists "profiles_update_privileged" on public.profiles;
create policy "profiles_update_privileged"
  on public.profiles for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

-- Profile row is created by trigger on auth.users (no self-insert needed)

-- Prospects
drop policy if exists "prospects_select" on public.prospects;
create policy "prospects_select"
  on public.prospects for select
  using (
    public.crm_is_privileged()
    or assigned_rep_id = auth.uid()
    or public.crm_is_team_member(assigned_rep_id)
  );

drop policy if exists "prospects_insert" on public.prospects;
create policy "prospects_insert"
  on public.prospects for insert
  with check (
    public.crm_is_privileged()
    or assigned_rep_id = auth.uid()
  );

drop policy if exists "prospects_update" on public.prospects;
create policy "prospects_update"
  on public.prospects for update
  using (
    public.crm_is_privileged()
    or assigned_rep_id = auth.uid()
    or public.crm_is_team_member(assigned_rep_id)
  )
  with check (
    public.crm_is_privileged()
    or assigned_rep_id = auth.uid()
    or public.crm_is_team_member(assigned_rep_id)
  );

drop policy if exists "prospects_delete" on public.prospects;
create policy "prospects_delete"
  on public.prospects for delete
  using (public.crm_is_privileged());

-- Clients
drop policy if exists "clients_select" on public.clients;
create policy "clients_select"
  on public.clients for select
  using (
    public.crm_is_privileged()
    or closing_rep_id = auth.uid()
    or public.crm_is_team_member(closing_rep_id)
  );

drop policy if exists "clients_insert" on public.clients;
create policy "clients_insert"
  on public.clients for insert
  with check (
    public.crm_is_privileged()
    or closing_rep_id = auth.uid()
  );

drop policy if exists "clients_update" on public.clients;
create policy "clients_update"
  on public.clients for update
  using (
    public.crm_is_privileged()
    or closing_rep_id = auth.uid()
  );

-- Activities
drop policy if exists "activities_select" on public.activities;
create policy "activities_select"
  on public.activities for select
  using (
    public.crm_is_privileged()
    or exists (
      select 1 from public.prospects pr
      where pr.id = activities.prospect_id
        and (
          pr.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(pr.assigned_rep_id)
        )
    )
  );

drop policy if exists "activities_insert" on public.activities;
create policy "activities_insert"
  on public.activities for insert
  with check (
    public.crm_is_privileged()
    or created_by = auth.uid()
  );

-- Notifications: own rows only
drop policy if exists "notifications_own" on public.notifications;
create policy "notifications_select_own"
  on public.notifications for select
  using (user_id = auth.uid() or public.crm_is_privileged());

drop policy if exists "notifications_update_own" on public.notifications;
create policy "notifications_update_own"
  on public.notifications for update
  using (user_id = auth.uid());

drop policy if exists "notifications_insert" on public.notifications;
create policy "notifications_insert"
  on public.notifications for insert
  with check (public.crm_is_privileged() or user_id = auth.uid());

-- Suppressions: CEO + HoS
drop policy if exists "suppressions_select" on public.suppressions;
create policy "suppressions_select"
  on public.suppressions for select
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role in ('ceo', 'hos'))
  );

drop policy if exists "suppressions_write" on public.suppressions;
create policy "suppressions_write"
  on public.suppressions for all
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role in ('ceo', 'hos'))
  );

-- Audit log: CEO only read
drop policy if exists "audit_select_ceo" on public.audit_log;
create policy "audit_select_ceo"
  on public.audit_log for select
  using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'ceo')
  );

-- ---------------------------------------------------------------------------
-- Trigger: new auth user → profile row
-- ---------------------------------------------------------------------------
create or replace function public.crm_handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
    coalesce(new.raw_user_meta_data->>'crm_role', 'sales_rep')
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = coalesce(excluded.full_name, public.profiles.full_name);
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_crm on auth.users;
create trigger on_auth_user_created_crm
  after insert on auth.users
  for each row execute function public.crm_handle_new_user();

-- ---------------------------------------------------------------------------
-- Realtime: prospect updates for pipeline (enable replication if needed)
-- ---------------------------------------------------------------------------
alter table public.prospects replica identity full;
alter publication supabase_realtime add table public.prospects;
