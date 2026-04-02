-- =============================================================================
-- HAWK CRM — run entire file in Supabase SQL Editor (or psql) in one go.
-- Order matches supabase/migrations/*.sql timestamp order.
-- If a statement fails (e.g. object already exists), fix or skip that block.
-- =============================================================================


-- >>> migrations/20260329000001_crm_phase1_core.sql <<<

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
    (select auth.uid()) = id
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role = 'team_lead' and public.profiles.team_lead_id = me.id
    )
  );

drop policy if exists "profiles_update_self" on public.profiles;
create policy "profiles_update_self"
  on public.profiles for update
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

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
drop policy if exists "notifications_select_own" on public.notifications;
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
do $realtime$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'prospects'
  ) then
    alter publication supabase_realtime add table public.prospects;
  end if;
end;
$realtime$;

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


-- >>> migrations/20260329000002_storage_reports_bucket.sql <<<

-- Storage bucket for PDF reports (create via Dashboard if this fails on permissions)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'reports',
  'reports',
  false,
  52428800,
  array['application/pdf', 'image/png', 'image/jpeg']::text[]
)
on conflict (id) do nothing;


-- >>> migrations/20260330000001_crm_phase2_prospect_profile.sql <<<

-- Phase 2 — Prospect profile: notes, files, scans, email events stub, onboarding, contact fields

alter table public.profiles
  add column if not exists onboarding_checklist jsonb default '{"whatsapp":false,"video":false,"first_prospect":false,"profile":false}'::jsonb;

alter table public.prospects
  add column if not exists contact_name text,
  add column if not exists contact_email text,
  add column if not exists phone text;

-- ---------------------------------------------------------------------------
-- Prospect notes (timeline + notes tab)
-- ---------------------------------------------------------------------------
create table if not exists public.prospect_notes (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  author_id uuid not null references public.profiles (id),
  body text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_prospect_notes_prospect on public.prospect_notes (prospect_id);
create index if not exists idx_prospect_notes_author on public.prospect_notes (author_id);

-- ---------------------------------------------------------------------------
-- Prospect files (URLs / attachments metadata)
-- ---------------------------------------------------------------------------
create table if not exists public.prospect_files (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  title text not null,
  file_url text not null,
  kind text default 'link' check (kind in ('link', 'pdf', 'loom', 'other')),
  created_by uuid references public.profiles (id),
  created_at timestamptz not null default now()
);

create index if not exists idx_prospect_files_prospect on public.prospect_files (prospect_id);

-- ---------------------------------------------------------------------------
-- CRM prospect scans (HAWK scanner results per prospect)
-- ---------------------------------------------------------------------------
create table if not exists public.crm_prospect_scans (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  hawk_score int,
  grade text,
  findings jsonb default '{}'::jsonb,
  status text not null default 'complete' check (status in ('pending', 'complete', 'failed')),
  triggered_by uuid references public.profiles (id),
  created_at timestamptz not null default now()
);

create index if not exists idx_crm_prospect_scans_prospect on public.crm_prospect_scans (prospect_id);

-- ---------------------------------------------------------------------------
-- Email events (Charlotte / Smartlead — populated in Phase 3)
-- ---------------------------------------------------------------------------
create table if not exists public.prospect_email_events (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  subject text,
  sent_at timestamptz,
  opened_at timestamptz,
  clicked_at timestamptz,
  replied_at timestamptz,
  sequence_step int,
  created_at timestamptz not null default now()
);

create index if not exists idx_prospect_email_events_prospect on public.prospect_email_events (prospect_id);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.prospect_notes enable row level security;
alter table public.prospect_files enable row level security;
alter table public.crm_prospect_scans enable row level security;
alter table public.prospect_email_events enable row level security;

drop policy if exists "prospect_notes_select" on public.prospect_notes;
create policy "prospect_notes_select"
  on public.prospect_notes for select
  using (
    public.crm_is_privileged()
    or (
      author_id = auth.uid()
      and exists (
        select 1 from public.prospects p
        where p.id = prospect_notes.prospect_id
          and (
            p.assigned_rep_id = auth.uid()
            or public.crm_is_team_member(p.assigned_rep_id)
          )
      )
    )
  );

drop policy if exists "prospect_notes_insert" on public.prospect_notes;
create policy "prospect_notes_insert"
  on public.prospect_notes for insert
  with check (
    author_id = auth.uid()
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

drop policy if exists "prospect_notes_update" on public.prospect_notes;
create policy "prospect_notes_update"
  on public.prospect_notes for update
  using (author_id = auth.uid())
  with check (author_id = auth.uid());

drop policy if exists "prospect_files_select" on public.prospect_files;
drop policy if exists "prospect_files_insert" on public.prospect_files;
drop policy if exists "prospect_files_delete" on public.prospect_files;
create policy "prospect_files_select"
  on public.prospect_files for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_files.prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

create policy "prospect_files_insert"
  on public.prospect_files for insert
  with check (
    created_by = auth.uid()
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

create policy "prospect_files_delete"
  on public.prospect_files for delete
  using (
    created_by = auth.uid()
    or public.crm_is_privileged()
  );

drop policy if exists "crm_scans_select" on public.crm_prospect_scans;
drop policy if exists "crm_scans_insert" on public.crm_prospect_scans;
create policy "crm_scans_select"
  on public.crm_prospect_scans for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = crm_prospect_scans.prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

create policy "crm_scans_insert"
  on public.crm_prospect_scans for insert
  with check (
    triggered_by = auth.uid()
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

drop policy if exists "email_events_select" on public.prospect_email_events;
create policy "email_events_select"
  on public.prospect_email_events for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_email_events.prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

-- Service role / Phase 3 will insert email events via backend

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


-- >>> migrations/20260330000002_prospect_notes_delete.sql <<<

-- Allow authors to delete their own prospect notes (matches update policy)

drop policy if exists "prospect_notes_delete" on public.prospect_notes;
create policy "prospect_notes_delete"
  on public.prospect_notes for delete
  using (author_id = auth.uid());


-- >>> migrations/20260331000001_crm_phase3_email_events_meta.sql <<<

-- Phase 3 — Email event metadata, dedupe key, source

alter table public.prospect_email_events
  add column if not exists source text not null default 'webhook',
  add column if not exists external_id text,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

comment on column public.prospect_email_events.source is 'smartlead | charlotte | webhook | manual';
comment on column public.prospect_email_events.external_id is 'Provider id for idempotent ingest (unique per prospect when set)';

create unique index if not exists idx_prospect_email_events_external_dedupe
  on public.prospect_email_events (prospect_id, external_id)
  where external_id is not null and length(trim(external_id)) > 0;


-- >>> migrations/20260401000001_crm_phase4_commissions.sql <<<

-- Phase 4 — Commissions: one row per client (30% of MRR at close), auto-created on client insert

create table if not exists public.crm_commissions (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  rep_id uuid not null references public.profiles (id),
  basis_mrr_cents int not null check (basis_mrr_cents >= 0),
  amount_cents int not null check (amount_cents >= 0),
  rate numeric(6,5) not null default 0.30,
  status text not null default 'pending' check (status in ('pending', 'approved', 'paid')),
  created_at timestamptz not null default now(),
  constraint crm_commissions_one_per_client unique (client_id)
);

create index if not exists idx_crm_commissions_rep on public.crm_commissions (rep_id);
create index if not exists idx_crm_commissions_created on public.crm_commissions (created_at desc);

alter table public.crm_commissions enable row level security;

drop policy if exists "crm_commissions_select" on public.crm_commissions;
create policy "crm_commissions_select"
  on public.crm_commissions for select
  using (
    public.crm_is_privileged()
    or rep_id = auth.uid()
    or public.crm_is_team_member(rep_id)
  );

drop policy if exists "crm_commissions_update" on public.crm_commissions;
create policy "crm_commissions_update"
  on public.crm_commissions for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

drop policy if exists "crm_commissions_delete" on public.crm_commissions;
create policy "crm_commissions_delete"
  on public.crm_commissions for delete
  using (public.crm_is_privileged());

-- Matches Close Won modal: 30% of first-month MRR
create or replace function public.crm_commission_from_client()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  amt int;
begin
  if new.closing_rep_id is null then
    return new;
  end if;
  amt := (new.mrr_cents * 30) / 100;
  insert into public.crm_commissions (client_id, rep_id, basis_mrr_cents, amount_cents, rate, status)
  values (new.id, new.closing_rep_id, new.mrr_cents, amt, 0.30, 'pending')
  on conflict (client_id) do nothing;
  return new;
end;
$$;

drop trigger if exists trg_clients_create_commission on public.clients;
create trigger trg_clients_create_commission
  after insert on public.clients
  for each row execute function public.crm_commission_from_client();


-- >>> migrations/20260401000002_realtime_scoreboard_tables.sql <<<

-- Realtime updates for live scoreboard (prospects already published in Phase 1)

alter table public.clients replica identity full;
alter table public.crm_commissions replica identity full;

do $realtime$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'clients'
  ) then
    alter publication supabase_realtime add table public.clients;
  end if;
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'crm_commissions'
  ) then
    alter publication supabase_realtime add table public.crm_commissions;
  end if;
end;
$realtime$;


-- >>> migrations/20260402000001_crm_support_tickets.sql <<<

-- Phase 8 — Internal support tickets (reps file; CEO/HoS triage via RLS + exec notifications)

create table if not exists public.crm_support_tickets (
  id uuid primary key default gen_random_uuid(),
  subject text not null,
  body text not null default '',
  status text not null default 'open' check (status in ('open', 'in_progress', 'resolved', 'closed')),
  priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),
  requester_id uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_crm_support_tickets_status on public.crm_support_tickets (status);
create index if not exists idx_crm_support_tickets_requester on public.crm_support_tickets (requester_id);
create index if not exists idx_crm_support_tickets_created on public.crm_support_tickets (created_at desc);

alter table public.crm_support_tickets enable row level security;

drop policy if exists "crm_support_tickets_select" on public.crm_support_tickets;
create policy "crm_support_tickets_select"
  on public.crm_support_tickets for select
  using (
    requester_id = auth.uid()
    or public.crm_is_privileged()
  );

drop policy if exists "crm_support_tickets_insert" on public.crm_support_tickets;
create policy "crm_support_tickets_insert"
  on public.crm_support_tickets for insert
  with check (requester_id = auth.uid());

drop policy if exists "crm_support_tickets_update" on public.crm_support_tickets;
create policy "crm_support_tickets_update"
  on public.crm_support_tickets for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

drop policy if exists "crm_support_tickets_delete" on public.crm_support_tickets;
create policy "crm_support_tickets_delete"
  on public.crm_support_tickets for delete
  using (public.crm_is_privileged());

create or replace function public.crm_support_tickets_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_crm_support_tickets_updated on public.crm_support_tickets;
create trigger trg_crm_support_tickets_updated
  before update on public.crm_support_tickets
  for each row execute function public.crm_support_tickets_set_updated_at();

-- Notify CEO + HoS when any ticket is created
create or replace function public.crm_notify_execs_new_ticket()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.notifications (user_id, title, message, type)
  select p.id,
         'New support ticket',
         left(new.subject, 200),
         'info'
  from public.profiles p
  where p.role in ('ceo', 'hos');
  return new;
end;
$$;

drop trigger if exists trg_crm_support_ticket_notify on public.crm_support_tickets;
create trigger trg_crm_support_ticket_notify
  after insert on public.crm_support_tickets
  for each row execute function public.crm_notify_execs_new_ticket();

-- Live bell updates (idempotent: skip if already in publication)
alter table public.notifications replica identity full;

do $realtime$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'notifications'
  ) then
    alter publication supabase_realtime add table public.notifications;
  end if;
end;
$realtime$;


-- >>> migrations/20260403000001_clients_company_name.sql <<<

-- Repair: legacy public.clients rows missing columns from phase1 (company_name, mrr_cents, etc.)

alter table public.clients add column if not exists prospect_id uuid;
alter table public.clients add column if not exists company_name text;
alter table public.clients add column if not exists domain text;
alter table public.clients add column if not exists plan text;
alter table public.clients add column if not exists mrr_cents integer;
alter table public.clients add column if not exists stripe_customer_id text;
alter table public.clients add column if not exists closing_rep_id uuid;
alter table public.clients add column if not exists status text;
alter table public.clients add column if not exists close_date timestamptz;
alter table public.clients add column if not exists created_at timestamptz;

update public.clients set mrr_cents = coalesce(mrr_cents, 0);
alter table public.clients alter column mrr_cents set default 0;
alter table public.clients alter column mrr_cents set not null;

update public.clients set status = coalesce(status, 'active');
alter table public.clients alter column status set default 'active';

update public.clients set close_date = coalesce(close_date, now());
alter table public.clients alter column close_date set default now();
alter table public.clients alter column close_date set not null;

update public.clients set created_at = coalesce(created_at, now());
alter table public.clients alter column created_at set default now();
alter table public.clients alter column created_at set not null;


-- >>> migrations/20260404000001_crm_phase1_invite_rr_stripe.sql <<<

-- Phase 1 — Rep invite lifecycle, round-robin, Stripe commission deferral

-- Profiles: assignment + onboarding gate + health score (health used in later phases)
alter table public.profiles
  add column if not exists last_assigned_at timestamptz,
  add column if not exists onboarding_completed_at timestamptz,
  add column if not exists health_score int check (health_score is null or (health_score >= 0 and health_score <= 100));

-- Extend CRM lifecycle status (invited → onboarding → active)
alter table public.profiles drop constraint if exists profiles_status_check;
alter table public.profiles
  add constraint profiles_status_check
  check (status in ('invited', 'onboarding', 'active', 'at_risk', 'inactive'));

-- Clients: defer commission until Stripe webhook when payment not verified at close
alter table public.clients
  add column if not exists commission_deferred boolean not null default false;

-- Existing active reps: treat as onboarded (avoid blocking pipeline after migration)
update public.profiles
set onboarding_completed_at = coalesce(onboarding_completed_at, now())
where status = 'active'
  and role in ('sales_rep', 'team_lead')
  and onboarding_completed_at is null;

-- Commission trigger: skip when deferred (webhook creates row later)
create or replace function public.crm_commission_from_client()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  amt int;
begin
  if new.closing_rep_id is null then
    return new;
  end if;
  if coalesce(new.commission_deferred, false) then
    return new;
  end if;
  amt := (new.mrr_cents * 30) / 100;
  insert into public.crm_commissions (client_id, rep_id, basis_mrr_cents, amount_cents, rate, status)
  values (new.id, new.closing_rep_id, new.mrr_cents, amt, 0.30, 'pending')
  on conflict (client_id) do nothing;
  return new;
end;
$$;

-- New auth users: honor CEO invite metadata (status + whatsapp prefilled)
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
begin
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


-- >>> migrations/20260405000001_crm_phase2_client_portal.sql <<<

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


-- >>> migrations/20260406000001_crm_phase3_monitor_reports.sql <<<

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


-- >>> migrations/20260407000001_crm_prospect_scans_scanner_v2.sql <<<

-- HAWK Scanner 2.0 — extended prospect scan payload (Railway pipeline + scoring)

alter table public.crm_prospect_scans
  add column if not exists scan_version text default '1.0',
  add column if not exists industry text,
  add column if not exists raw_layers jsonb not null default '{}'::jsonb,
  add column if not exists interpreted_findings jsonb not null default '[]'::jsonb,
  add column if not exists breach_cost_estimate jsonb not null default '{}'::jsonb,
  add column if not exists external_job_id text;


-- >>> migrations/20260408000001_profiles_rls_ceo_anchor.sql <<<

drop policy if exists "profiles_select_own_or_privileged" on public.profiles;
create policy "profiles_select_own_or_privileged"
  on public.profiles for select
  using (
    (select auth.uid()) = id
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role = 'team_lead' and public.profiles.team_lead_id = me.id
    )
  );

drop policy if exists "profiles_update_self" on public.profiles;
create policy "profiles_update_self"
  on public.profiles for update
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

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


-- >>> migrations/20260408000002_crm_scan_attack_paths_placeholder.sql <<<

alter table public.crm_prospect_scans
  add column if not exists attack_paths jsonb not null default '[]'::jsonb;

comment on column public.crm_prospect_scans.attack_paths is 'Top attack paths narrative (2B); JSON array of {name, steps, likelihood, impact}';


-- >>> migrations/20260409000001_client_shield_monitoring.sql <<<

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


-- >>> migrations/20260411000001_charlotte_automation.sql >>>

create table if not exists public.crm_settings (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

insert into public.crm_settings (key, value)
values ('charlotte_industry_day_index', '0')
on conflict (key) do nothing;

insert into public.crm_settings (key, value)
values ('smartlead_campaign_id', '')
on conflict (key) do nothing;

create table if not exists public.charlotte_runs (
  id uuid primary key default gen_random_uuid(),
  run_date date not null default ((timezone('America/Edmonton', now()))::date),
  industry text,
  leads_pulled integer not null default 0,
  emails_verified integer not null default 0,
  emails_suppressed integer not null default 0,
  domains_scanned integer not null default 0,
  scan_failures integer not null default 0,
  emails_written integer not null default 0,
  leads_uploaded integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_charlotte_runs_created on public.charlotte_runs (created_at desc);
create index if not exists idx_charlotte_runs_date on public.charlotte_runs (run_date desc);

alter table public.charlotte_runs enable row level security;

-- >>> migrations/20260412000001_hawk_scale_architecture.sql >>>

create table if not exists public.scanner_failures (
  id uuid primary key default gen_random_uuid(),
  domain text not null,
  error_message text,
  layer text,
  scan_depth text,
  created_at timestamptz not null default now()
);
create index if not exists idx_scanner_failures_domain on public.scanner_failures (domain);
create index if not exists idx_scanner_failures_created on public.scanner_failures (created_at desc);
alter table public.scanner_failures enable row level security;

create table if not exists public.scanner_health_logs (
  id uuid primary key default gen_random_uuid(),
  checked_at timestamptz not null default now(),
  queue_depth integer,
  avg_completion_seconds numeric,
  failure_rate_pct numeric,
  workers_active integer,
  alert_sent boolean not null default false
);
create index if not exists idx_scanner_health_logs_checked on public.scanner_health_logs (checked_at desc);
alter table public.scanner_health_logs enable row level security;

create table if not exists public.charlotte_emails (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references public.charlotte_runs (id) on delete set null,
  prospect_domain text not null,
  prospect_email text,
  prospect_industry text,
  hawk_score integer,
  top_finding text,
  email_subject text,
  email_body text,
  word_count integer,
  has_dashes boolean not null default false,
  has_bullets boolean not null default false,
  contains_domain boolean not null default true,
  contains_score boolean not null default true,
  smartlead_lead_id text,
  created_at timestamptz not null default now()
);
create index if not exists idx_charlotte_emails_run on public.charlotte_emails (run_id);
create index if not exists idx_charlotte_emails_created on public.charlotte_emails (created_at desc);
alter table public.charlotte_emails enable row level security;

create table if not exists public.scanner_cache (
  domain text not null,
  scan_depth text not null,
  result jsonb not null,
  cached_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '24 hours'),
  primary key (domain, scan_depth)
);
create index if not exists idx_scanner_cache_expires on public.scanner_cache (expires_at);
alter table public.scanner_cache enable row level security;

alter table public.charlotte_runs
  add column if not exists scan_skipped integer not null default 0,
  add column if not exists email_failed integer not null default 0,
  add column if not exists upload_failed integer not null default 0;

alter table public.prospects
  add column if not exists reply_received_at timestamptz,
  add column if not exists va_actioned_at timestamptz,
  add column if not exists reply_response_minutes integer,
  add column if not exists va_snooze_until timestamptz,
  add column if not exists va_escalation_sent_at timestamptz;

create index if not exists idx_prospects_reply_sla
  on public.prospects (reply_received_at)
  where va_actioned_at is null and reply_received_at is not null;

alter table public.clients
  add column if not exists onboarding_call_booked_at timestamptz,
  add column if not exists onboarding_call_completed_at timestamptz,
  add column if not exists onboarded_at timestamptz,
  add column if not exists week_one_score_start integer,
  add column if not exists week_one_score_end integer;

insert into public.crm_settings (key, value)
values ('charlotte_estimated_reply_rate', '0.02')
on conflict (key) do nothing;

drop policy if exists "scanner_health_logs_ceo_select" on public.scanner_health_logs;
create policy "scanner_health_logs_ceo_select"
  on public.scanner_health_logs for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.role in ('ceo', 'hos')
    )
  );

drop policy if exists "scanner_failures_ceo_select" on public.scanner_failures;
create policy "scanner_failures_ceo_select"
  on public.scanner_failures for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.role in ('ceo', 'hos')
    )
  );

drop policy if exists "charlotte_emails_ceo_select" on public.charlotte_emails;
create policy "charlotte_emails_ceo_select"
  on public.charlotte_emails for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.role in ('ceo', 'hos')
    )
  );

drop policy if exists "scanner_cache_ceo_select" on public.scanner_cache;
create policy "scanner_cache_ceo_select"
  on public.scanner_cache for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.role in ('ceo', 'hos')
    )
  );

drop policy if exists "charlotte_runs_ceo_select" on public.charlotte_runs;
create policy "charlotte_runs_ceo_select"
  on public.charlotte_runs for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = (select auth.uid()) and p.role in ('ceo', 'hos')
    )
  );

-- >>> migrations/20260414000001_shield_day0_columns.sql >>>

alter table public.clients
  add column if not exists certification_eligible_at timestamptz;

comment on column public.clients.certification_eligible_at is 'onboarded_at + 90 days — eligibility date for HAWK Certified';

-- >>> migrations/20260415000001_onboarding_sequence_tracking.sql >>>

alter table public.clients
  add column if not exists onboarding_day1_sent_at timestamptz,
  add column if not exists onboarding_day3_sent_at timestamptz,
  add column if not exists onboarding_day7_sent_at timestamptz;

comment on column public.clients.onboarding_day1_sent_at is '24h+ reminder: call booking + first findings email';
comment on column public.clients.onboarding_day3_sent_at is '72h progress WhatsApp';
comment on column public.clients.onboarding_day7_sent_at is 'Week one summary WhatsApp + email';

-- >>> migrations/20260410000001_profiles_role_closer.sql >>>

alter table public.profiles drop constraint if exists profiles_role_check;

alter table public.profiles
  add constraint profiles_role_check
  check (role in ('ceo', 'hos', 'team_lead', 'sales_rep', 'closer'));

-- >>> OPTIONAL: verify RLS policies (read-only) — from tests/crm_phase1_rls.sql <<<

select tablename, policyname, cmd, qual, with_check
from pg_policies
where schemaname = 'public' and tablename in ('prospects', 'profiles', 'clients', 'activities')
order by tablename, policyname;
