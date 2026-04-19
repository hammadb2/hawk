-- =============================================================================
-- hawk_complete_schema.sql — HAWK + CRM + ARIA + Guardian (Supabase / Postgres)
-- =============================================================================
-- Generated: concatenation of supabase/migrations/*.sql in filename order, plus
-- this header. Re-run safe after migrations 20260501000001 (enum/index/policy
-- idempotency), 20260430000001 (DROP POLICY + WITH CHECK), 20260504000001
-- (code alignment view/table), and 20260401000002 (realtime publication add
-- guarded via pg_publication_tables — avoids 42710 if clients is already published).
--
-- AUDIT SUMMARY (2026-04-18)
-- -------------------------
-- The legacy paste file supabase/run_all_crm_migrations.sql stopped before many
-- later migrations; the following were referenced from application code but
-- absent there — they ARE included via the ordered migrations in this file:
--   aria_action_log, aria_conversations, aria_messages, aria_scheduled_actions,
--   aria_client_health_scores, aria_proactive_briefings, aria_pipeline_runs,
--   aria_pipeline_leads, aria_user_patterns, aria_lead_inventory,
--   aria_inbound_replies, aria_domain_health, aria_memories (+ vector RPC),
--   aria_whatsapp_messages, aria_whatsapp_queue, aria_ab_experiments,
--   aria_competitive_intel, aria_playbooks, aria_training_sessions,
--   aria_webhooks, aria_api_keys, client_attacker_simulation_reports,
--   client_competitor_benchmarks, client_dnstwist_snapshots, client_domain_scans,
--   client_security_milestones, client_threat_briefings, portal_finding_status,
--   onboarding_documents, onboarding_quiz_results, onboarding_sessions,
--   onboarding_submissions, team_bank_details, team_personal_details,
--   prospect pipeline columns (20260502000001), guardian tables (20260503000001).
-- crm_notifications: only aria_inbox_health.py used this path; it was missing
-- from DB — added in 20260504000001_schema_compat_code_alignment.sql.
-- prospect_scans: aria_memory.py queried this table name; physical table is
-- crm_prospect_scans — compatibility VIEW added in the same migration.
-- Remaining app issues (not DDL): e.g. frontend crm_settings row uses .eq("id")
-- while PK is "key" — fix in TS separately.
--
-- DEPENDENCY ORDER: migrations are timestamp-prefixed; do not reorder.
-- PREREQ: Supabase project (auth schema exists). Enables extensions: pgcrypto,
-- vector (extensions schema).
-- =============================================================================


-- >>> SOURCE: 20260329000001_crm_phase1_core.sql <<<
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

-- ---------------------------------------------------------------------------
-- CEO profile anchor (repeat in any migration that touches profiles)
-- ---------------------------------------------------------------------------
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

-- >>> SOURCE: 20260329000002_storage_reports_bucket.sql <<<
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

-- >>> SOURCE: 20260330000001_crm_phase2_prospect_profile.sql <<<
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

-- >>> SOURCE: 20260330000002_prospect_notes_delete.sql <<<
-- Allow authors to delete their own prospect notes (matches update policy)

drop policy if exists "prospect_notes_delete" on public.prospect_notes;
create policy "prospect_notes_delete"
  on public.prospect_notes for delete
  using (author_id = auth.uid());

-- >>> SOURCE: 20260331000001_crm_phase3_email_events_meta.sql <<<
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

-- >>> SOURCE: 20260401000001_crm_phase4_commissions.sql <<<
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

-- >>> SOURCE: 20260401000002_realtime_scoreboard_tables.sql <<<
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
end;
$realtime$;

do $realtime$
begin
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

-- >>> SOURCE: 20260402000001_crm_support_tickets.sql <<<
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

-- Live bell updates (ignore if already in publication)
alter table public.notifications replica identity full;

do $pub$
begin
  alter publication supabase_realtime add table public.notifications;
exception
  when duplicate_object then
    null;
end;
$pub$;

-- >>> SOURCE: 20260403000001_clients_company_name.sql <<<
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

-- >>> SOURCE: 20260403000002_prospects_homepage_scanner.sql <<<
-- Homepage scanner leads: source value + optional top_finding on prospects

alter table public.prospects
  add column if not exists top_finding text;

alter table public.prospects drop constraint if exists prospects_source_check;
alter table public.prospects add constraint prospects_source_check
  check (source in ('charlotte', 'manual', 'inbound', 'homepage_scanner'));

-- >>> SOURCE: 20260404000001_crm_phase1_invite_rr_stripe.sql <<<
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

-- >>> SOURCE: 20260404000001_guarantee_verification_codes.sql <<<
-- Email verification codes for gated Breach Response Guarantee document (public marketing)

create table if not exists public.guarantee_verification_codes (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  full_name text not null,
  company text not null,
  code_hash text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_guarantee_ver_email_created
  on public.guarantee_verification_codes (lower(email), created_at desc);

alter table public.guarantee_verification_codes enable row level security;

-- No anon/authenticated policies — backend uses service role only

-- >>> SOURCE: 20260405000001_crm_phase2_client_portal.sql <<<
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

-- >>> SOURCE: 20260406000001_crm_phase3_monitor_reports.sql <<<
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

-- >>> SOURCE: 20260406120000_clients_billing_status.sql <<<
-- Portal paywall: account-first flow — block app until subscription is active.

alter table public.clients
  add column if not exists billing_status text not null default 'pending_payment';

comment on column public.clients.billing_status is
  'pending_payment = signed up, not subscribed yet; active = paid / entitled; past_due = payment failed';

-- Existing paying customers (legacy) should not be stuck behind the paywall.
update public.clients
set billing_status = 'active'
where coalesce(mrr_cents, 0) > 0
  and billing_status = 'pending_payment';

-- >>> SOURCE: 20260406130000_clients_plan_check.sql <<<
-- Portal / checkout insert plan slugs (shield, starter, hawk_*). Drop strict check if it rejects them.
alter table public.clients drop constraint if exists clients_plan_check;

-- >>> SOURCE: 20260407000001_crm_prospect_scans_scanner_v2.sql <<<
-- HAWK Scanner 2.0 — extended prospect scan payload (Railway pipeline + scoring)

alter table public.crm_prospect_scans
  add column if not exists scan_version text default '1.0',
  add column if not exists industry text,
  add column if not exists raw_layers jsonb not null default '{}'::jsonb,
  add column if not exists interpreted_findings jsonb not null default '[]'::jsonb,
  add column if not exists breach_cost_estimate jsonb not null default '{}'::jsonb,
  add column if not exists external_job_id text;

comment on column public.crm_prospect_scans.scan_version is 'Scanner release, e.g. 2.0';
comment on column public.crm_prospect_scans.industry is 'Industry label for risk multiplier (dental, medical, legal, financial, etc.)';
comment on column public.crm_prospect_scans.raw_layers is 'Per-layer tool output (subfinder, naabu, httpx, nuclei, …)';
comment on column public.crm_prospect_scans.interpreted_findings is 'Claude interpretations with fix guides per finding';
comment on column public.crm_prospect_scans.breach_cost_estimate is 'IBM-style sector breach cost context + inputs used';
comment on column public.crm_prospect_scans.external_job_id is 'Queue job id on Railway scanner worker';

-- >>> SOURCE: 20260408000001_profiles_rls_ceo_anchor.sql <<<
-- Idempotent fix: profiles SELECT must use (select auth.uid()) = id to avoid RLS recursion.
-- Safe on DBs that already ran older migrations with id = auth.uid().

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

-- >>> SOURCE: 20260408000002_crm_scan_attack_paths_placeholder.sql <<<
-- 2B prep — attack path chaining (Claude) stored per scan; UI in roadmap
alter table public.crm_prospect_scans
  add column if not exists attack_paths jsonb not null default '[]'::jsonb;

comment on column public.crm_prospect_scans.attack_paths is 'Top attack paths narrative (2B); JSON array of {name, steps, likelihood, impact}';

-- >>> SOURCE: 20260409000001_client_shield_monitoring.sql <<<
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

-- >>> SOURCE: 20260410000001_profiles_role_closer.sql <<<
-- Charlotte round-robin: allow profiles.role = 'closer' (in addition to sales_rep, etc.)

alter table public.profiles drop constraint if exists profiles_role_check;

alter table public.profiles
  add constraint profiles_role_check
  check (role in ('ceo', 'hos', 'team_lead', 'sales_rep', 'closer'));

-- >>> SOURCE: 20260411000001_charlotte_automation.sql <<<
-- Charlotte full automation: settings (industry rotation, optional Smartlead campaign id) + run logs

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

-- >>> SOURCE: 20260412000001_hawk_scale_architecture.sql <<<
-- HAWK scale architecture: scanner health, failures, Charlotte email QA, VA reply tracking, cache, client onboarding columns

-- Scanner failures (worker + API can insert via service role)
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

-- Scanner health cron samples
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

-- Charlotte email quality (one row per lead uploaded)
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

-- Optional SQL cache mirror (primary cache is Redis in production)
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

-- charlotte_runs: granular failure counts + estimated reply rate source
alter table public.charlotte_runs
  add column if not exists scan_skipped integer not null default 0,
  add column if not exists email_failed integer not null default 0,
  add column if not exists upload_failed integer not null default 0;

-- VA reply SLA
alter table public.prospects
  add column if not exists reply_received_at timestamptz,
  add column if not exists va_actioned_at timestamptz,
  add column if not exists reply_response_minutes integer,
  add column if not exists va_snooze_until timestamptz,
  add column if not exists va_escalation_sent_at timestamptz;

create index if not exists idx_prospects_reply_sla
  on public.prospects (reply_received_at)
  where va_actioned_at is null and reply_received_at is not null;

-- Client onboarding (automated sequence)
alter table public.clients
  add column if not exists onboarding_call_booked_at timestamptz,
  add column if not exists onboarding_call_completed_at timestamptz,
  add column if not exists onboarded_at timestamptz,
  add column if not exists week_one_score_start integer,
  add column if not exists week_one_score_end integer;

-- Settings: estimated Charlotte reply rate for CEO summary (e.g. 0.02 = 2%)
insert into public.crm_settings (key, value)
values ('charlotte_estimated_reply_rate', '0.02')
on conflict (key) do nothing;

-- RLS: CRM privileged roles can read monitoring tables
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

-- charlotte_runs: allow CEO to read (was RLS-on with no policy)
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

-- >>> SOURCE: 20260414000001_shield_day0_columns.sql <<<
-- Shield Day 0 / certification timeline (set when Stripe confirms Shield subscription payment)
alter table public.clients
  add column if not exists certification_eligible_at timestamptz;

comment on column public.clients.certification_eligible_at is 'onboarded_at + 90 days — eligibility date for HAWK Certified';

-- >>> SOURCE: 20260415000001_onboarding_sequence_tracking.sql <<<
-- Idempotent Shield onboarding Day 1 / 3 / 7 sends (cron marks timestamps)
alter table public.clients
  add column if not exists onboarding_day1_sent_at timestamptz,
  add column if not exists onboarding_day3_sent_at timestamptz,
  add column if not exists onboarding_day7_sent_at timestamptz;

comment on column public.clients.onboarding_day1_sent_at is '24h+ reminder: call booking + first findings email';
comment on column public.clients.onboarding_day3_sent_at is '72h progress WhatsApp';
comment on column public.clients.onboarding_day7_sent_at is 'Week one summary WhatsApp + email';

-- >>> SOURCE: 20260416000001_readiness_guarantee.sql <<<
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

-- >>> SOURCE: 20260417000001_profiles_role_client.sql <<<
-- Portal end-users: role = client (never sales roles). CRM staff remain ceo|hos|team_lead|sales_rep|closer.

alter table public.profiles drop constraint if exists profiles_role_check;

alter table public.profiles
  add constraint profiles_role_check
  check (role in ('ceo', 'hos', 'team_lead', 'sales_rep', 'closer', 'client'));

-- Invite with raw_user_meta_data.portal_client_id: create portal profile row with role client
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
    insert into public.profiles (id, email, full_name, role, status)
    values (
      new.id,
      new.email,
      coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
      'client',
      'active'
    )
    on conflict (id) do update
      set email = excluded.email,
          full_name = coalesce(excluded.full_name, public.profiles.full_name),
          role = 'client',
          status = 'active';
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

-- >>> SOURCE: 20260418000001_portal_phase2_sticky.sql <<<
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

-- >>> SOURCE: 20260421000001_client_dnstwist_snapshots.sql <<<
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

-- >>> SOURCE: 20260422000001_phase4_enterprise_attacker.sql <<<
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

-- >>> SOURCE: 20260423000001_prospects_last_aging_nudge.sql <<<
-- Go-live: throttle repeated aging WhatsApp nudges per prospect

alter table public.prospects
  add column if not exists last_aging_nudge_at timestamptz;

comment on column public.prospects.last_aging_nudge_at is 'Last time aging cron sent WhatsApp for 10+ day inactivity; next nudge after 48h';

-- >>> SOURCE: 20260424000001_portal_guarantee_acceptance.sql <<<
-- Portal: record Breach Response Guarantee acceptance (blocks dashboard until accepted once)

alter table public.client_portal_profiles
  add column if not exists guarantee_terms_accepted_at timestamptz;

comment on column public.client_portal_profiles.guarantee_terms_accepted_at is
  'When the portal user acknowledged the guarantee summary; required before main portal UI.';

drop policy if exists "client_portal_profiles_update_own_acceptance" on public.client_portal_profiles;
create policy "client_portal_profiles_update_own_acceptance"
  on public.client_portal_profiles for update
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- >>> SOURCE: 20260425000001_profiles_role_type_va_rls.sql <<<
-- VA / VA Manager — role_type on profiles + prospect access for VA manager + RLS updates

-- ---------------------------------------------------------------------------
-- 1) Column: role_type (orthogonal to sales `role`: ceo|hos|team_lead|sales_rep|closer|client)
-- ---------------------------------------------------------------------------
alter table public.profiles
  add column if not exists role_type text;

update public.profiles set role_type = 'closer' where role_type is null;

update public.profiles set role_type = 'ceo' where role = 'ceo';
update public.profiles set role_type = 'client' where role = 'client';

alter table public.profiles alter column role_type set default 'closer';
alter table public.profiles alter column role_type set not null;

alter table public.profiles drop constraint if exists profiles_role_type_check;
alter table public.profiles
  add constraint profiles_role_type_check
  check (role_type in ('ceo', 'closer', 'va_outreach', 'va_manager', 'csm', 'client'));

create index if not exists idx_profiles_role_type on public.profiles (role_type);

comment on column public.profiles.role_type is
  'Functional bucket: VA outreach, VA manager, CSM, closer, CEO, client. Used with `role` (CRM seat).';

-- ---------------------------------------------------------------------------
-- 2) Prospect access — includes VA manager viewing prospects assigned to VA team
-- ---------------------------------------------------------------------------
create or replace function public.crm_can_access_prospect(prospect_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    public.crm_is_privileged()
    or exists (
      select 1 from public.prospects pr
      where pr.id = prospect_id
        and (
          pr.assigned_rep_id = (select auth.uid())
          or public.crm_is_team_member(pr.assigned_rep_id)
        )
    )
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.prospects pr
      inner join public.profiles rep on rep.id = pr.assigned_rep_id
      where pr.id = prospect_id
        and rep.role_type in ('va_outreach', 'va_manager')
    ),
    false
  );
$$;

-- ---------------------------------------------------------------------------
-- 3) profiles — VA manager can list VA team; cannot use ceo/hos financial privileges
-- ---------------------------------------------------------------------------
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
    or (
      exists (
        select 1 from public.profiles me
        where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      )
      and public.profiles.role_type in ('va_outreach', 'va_manager')
    )
  );

drop policy if exists "profiles_update_va_manager_team" on public.profiles;
create policy "profiles_update_va_manager_team"
  on public.profiles for update
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and public.profiles.role_type in ('va_outreach', 'va_manager')
    and public.profiles.role <> 'ceo'
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and public.profiles.role_type in ('va_outreach', 'va_manager')
    and public.profiles.role <> 'ceo'
  );

-- ---------------------------------------------------------------------------
-- 4) prospects
-- ---------------------------------------------------------------------------
drop policy if exists "prospects_select" on public.prospects;
create policy "prospects_select"
  on public.prospects for select
  using (public.crm_can_access_prospect(id));

drop policy if exists "prospects_insert" on public.prospects;
create policy "prospects_insert"
  on public.prospects for insert
  with check (
    public.crm_is_privileged()
    or assigned_rep_id = (select auth.uid())
  );

drop policy if exists "prospects_update" on public.prospects;
create policy "prospects_update"
  on public.prospects for update
  using (public.crm_can_access_prospect(id))
  with check (public.crm_can_access_prospect(id));

drop policy if exists "prospects_delete" on public.prospects;
create policy "prospects_delete"
  on public.prospects for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 5) activities
-- ---------------------------------------------------------------------------
drop policy if exists "activities_select" on public.activities;
create policy "activities_select"
  on public.activities for select
  using (
    public.crm_is_privileged()
    or exists (
      select 1 from public.prospects pr
      where pr.id = activities.prospect_id
        and public.crm_can_access_prospect(pr.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 6) prospect_notes — keep author-only for reps; VA manager reads notes on VA queue
-- ---------------------------------------------------------------------------
drop policy if exists "prospect_notes_select" on public.prospect_notes;
create policy "prospect_notes_select"
  on public.prospect_notes for select
  using (
    public.crm_is_privileged()
    or (
      author_id = (select auth.uid())
      and exists (
        select 1 from public.prospects p
        where p.id = prospect_notes.prospect_id
          and (
            p.assigned_rep_id = (select auth.uid())
            or public.crm_is_team_member(p.assigned_rep_id)
          )
      )
    )
    or (
      exists (
        select 1 from public.profiles me
        where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      )
      and exists (
        select 1 from public.prospects p
        where p.id = prospect_notes.prospect_id
          and exists (
            select 1 from public.profiles rep
            where rep.id = p.assigned_rep_id
              and rep.role_type in ('va_outreach', 'va_manager')
          )
      )
    )
  );

drop policy if exists "prospect_notes_insert" on public.prospect_notes;
create policy "prospect_notes_insert"
  on public.prospect_notes for insert
  with check (
    author_id = (select auth.uid())
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = (select auth.uid())
          or public.crm_is_team_member(p.assigned_rep_id)
          or public.crm_can_access_prospect(p.id)
        )
    )
  );

-- ---------------------------------------------------------------------------
-- 7) prospect_files
-- ---------------------------------------------------------------------------
drop policy if exists "prospect_files_select" on public.prospect_files;
create policy "prospect_files_select"
  on public.prospect_files for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_files.prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

drop policy if exists "prospect_files_insert" on public.prospect_files;
create policy "prospect_files_insert"
  on public.prospect_files for insert
  with check (
    created_by = (select auth.uid())
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 8) crm_prospect_scans
-- ---------------------------------------------------------------------------
drop policy if exists "crm_scans_select" on public.crm_prospect_scans;
create policy "crm_scans_select"
  on public.crm_prospect_scans for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = crm_prospect_scans.prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

drop policy if exists "crm_scans_insert" on public.crm_prospect_scans;
create policy "crm_scans_insert"
  on public.crm_prospect_scans for insert
  with check (
    triggered_by = (select auth.uid())
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 9) prospect_email_events
-- ---------------------------------------------------------------------------
drop policy if exists "email_events_select" on public.prospect_email_events;
create policy "email_events_select"
  on public.prospect_email_events for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_email_events.prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 10) Auth trigger — set role_type for portal clients + optional crm_role_type metadata
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
  meta_rt text;
begin
  portal_cid := nullif(trim(coalesce(new.raw_user_meta_data->>'portal_client_id', '')), '');
  if portal_cid is not null and portal_cid <> '' then
    insert into public.profiles (id, email, full_name, role, status, role_type)
    values (
      new.id,
      new.email,
      coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
      'client',
      'active',
      'client'
    )
    on conflict (id) do update
      set email = excluded.email,
          full_name = coalesce(excluded.full_name, public.profiles.full_name),
          role = 'client',
          role_type = 'client',
          status = 'active';
    return new;
  end if;

  initial_status := nullif(trim(lower(coalesce(new.raw_user_meta_data->>'crm_initial_status', ''))), '');
  wa := nullif(trim(coalesce(new.raw_user_meta_data->>'whatsapp_number', '')), '');
  begin
    tl := (new.raw_user_meta_data->>'crm_team_lead_id')::uuid;
  exception when others then
    tl := null;
  end;

  meta_rt := nullif(trim(lower(coalesce(new.raw_user_meta_data->>'crm_role_type', ''))), '');
  if meta_rt not in ('ceo', 'closer', 'va_outreach', 'va_manager', 'csm', 'client') then
    meta_rt := null;
  end if;

  insert into public.profiles (id, email, full_name, role, status, whatsapp_number, team_lead_id, role_type)
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
    tl,
    coalesce(meta_rt, 'closer')
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = coalesce(excluded.full_name, public.profiles.full_name);
  return new;
end;
$$;

-- >>> SOURCE: 20260426000001_ai_onboarding_command_center.sql <<<
-- AI Onboarding Portal + AI Command Center — tables, storage, RLS
-- =========================================================================

-- ---------------------------------------------------------------------------
-- 1) team_personal_details — personal info collected during onboarding
-- ---------------------------------------------------------------------------
create table if not exists public.team_personal_details (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  phone text,
  whatsapp text,
  address text,
  country text,
  date_of_birth date,
  emergency_contact_name text,
  emergency_contact_phone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id)
);

alter table public.team_personal_details enable row level security;

drop policy if exists "tpd_select" on public.team_personal_details;
create policy "tpd_select"
  on public.team_personal_details for select
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      and exists (
        select 1 from public.profiles t
        where t.id = team_personal_details.profile_id and t.role_type in ('va_outreach', 'va_manager')
      )
    )
  );

drop policy if exists "tpd_insert" on public.team_personal_details;
create policy "tpd_insert"
  on public.team_personal_details for insert
  with check (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "tpd_update" on public.team_personal_details;
create policy "tpd_update"
  on public.team_personal_details for update
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

-- ---------------------------------------------------------------------------
-- 2) team_bank_details — bank info collected during onboarding
-- ---------------------------------------------------------------------------
create table if not exists public.team_bank_details (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  full_name text,
  bank_name text,
  account_number text,
  routing_or_swift text,
  payment_method text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id)
);

alter table public.team_bank_details enable row level security;

drop policy if exists "tbd_select" on public.team_bank_details;
create policy "tbd_select"
  on public.team_bank_details for select
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "tbd_insert" on public.team_bank_details;
create policy "tbd_insert"
  on public.team_bank_details for insert
  with check (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "tbd_update" on public.team_bank_details;
create policy "tbd_update"
  on public.team_bank_details for update
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

-- ---------------------------------------------------------------------------
-- 3) onboarding_sessions
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_sessions (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'in_progress'
    check (status in ('in_progress', 'pending_review', 'approved', 'rejected')),
  agreed_terms jsonb default '{}'::jsonb,
  current_step int not null default 1,
  completed_at timestamptz,
  approved_by uuid references public.profiles (id),
  approved_at timestamptz,
  rejected_reason text,
  created_at timestamptz not null default now(),
  unique (profile_id)
);

create index if not exists idx_onboarding_sessions_profile on public.onboarding_sessions (profile_id);
create index if not exists idx_onboarding_sessions_status on public.onboarding_sessions (status);

alter table public.onboarding_sessions enable row level security;

drop policy if exists "obs_select" on public.onboarding_sessions;
create policy "obs_select"
  on public.onboarding_sessions for select
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      and exists (
        select 1 from public.profiles t
        where t.id = onboarding_sessions.profile_id and t.role_type in ('va_outreach', 'va_manager')
      )
    )
  );

drop policy if exists "obs_insert" on public.onboarding_sessions;
create policy "obs_insert"
  on public.onboarding_sessions for insert
  with check (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "obs_update" on public.onboarding_sessions;
create policy "obs_update"
  on public.onboarding_sessions for update
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      and exists (
        select 1 from public.profiles t
        where t.id = onboarding_sessions.profile_id and t.role_type in ('va_outreach', 'va_manager')
      )
    )
  );

-- ---------------------------------------------------------------------------
-- 4) onboarding_documents — signed contracts, NDAs, AUPs
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_documents (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.onboarding_sessions (id) on delete cascade,
  document_type text not null
    check (document_type in ('contract', 'nda', 'acceptable_use')),
  file_url text,
  signed_at timestamptz,
  signature_data text,
  ip_address text,
  created_at timestamptz not null default now()
);

create index if not exists idx_onboarding_docs_session on public.onboarding_documents (session_id);

alter table public.onboarding_documents enable row level security;

drop policy if exists "obd_select" on public.onboarding_documents;
create policy "obd_select"
  on public.onboarding_documents for select
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_documents.session_id
        and (
          s.profile_id = (select auth.uid())
          or public.crm_is_privileged()
          or exists (
            select 1 from public.profiles me
            where me.id = (select auth.uid()) and me.role_type = 'va_manager'
            and exists (
              select 1 from public.profiles t
              where t.id = s.profile_id and t.role_type in ('va_outreach', 'va_manager')
            )
          )
        )
    )
  );

drop policy if exists "obd_insert" on public.onboarding_documents;
create policy "obd_insert"
  on public.onboarding_documents for insert
  with check (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

drop policy if exists "obd_update" on public.onboarding_documents;
create policy "obd_update"
  on public.onboarding_documents for update
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_documents.session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

-- ---------------------------------------------------------------------------
-- 5) onboarding_submissions — government ID + bank/personal flags
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_submissions (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.onboarding_sessions (id) on delete cascade,
  government_id_url text,
  bank_details_submitted boolean not null default false,
  personal_details_submitted boolean not null default false,
  created_at timestamptz not null default now(),
  unique (session_id)
);

alter table public.onboarding_submissions enable row level security;

drop policy if exists "obsub_select" on public.onboarding_submissions;
create policy "obsub_select"
  on public.onboarding_submissions for select
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_submissions.session_id
        and (
          s.profile_id = (select auth.uid())
          or public.crm_is_privileged()
          or exists (
            select 1 from public.profiles me
            where me.id = (select auth.uid()) and me.role_type = 'va_manager'
            and exists (
              select 1 from public.profiles t
              where t.id = s.profile_id and t.role_type in ('va_outreach', 'va_manager')
            )
          )
        )
    )
  );

drop policy if exists "obsub_insert" on public.onboarding_submissions;
create policy "obsub_insert"
  on public.onboarding_submissions for insert
  with check (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

drop policy if exists "obsub_update" on public.onboarding_submissions;
create policy "obsub_update"
  on public.onboarding_submissions for update
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_submissions.session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

-- ---------------------------------------------------------------------------
-- 6) onboarding_quiz_results
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_quiz_results (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.onboarding_sessions (id) on delete cascade,
  module text not null,
  score int not null default 0,
  passed boolean not null default false,
  completed_at timestamptz
);

create index if not exists idx_quiz_results_session on public.onboarding_quiz_results (session_id);

alter table public.onboarding_quiz_results enable row level security;

drop policy if exists "oqr_select" on public.onboarding_quiz_results;
create policy "oqr_select"
  on public.onboarding_quiz_results for select
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_quiz_results.session_id
        and (
          s.profile_id = (select auth.uid())
          or public.crm_is_privileged()
          or exists (
            select 1 from public.profiles me
            where me.id = (select auth.uid()) and me.role_type = 'va_manager'
            and exists (
              select 1 from public.profiles t
              where t.id = s.profile_id and t.role_type in ('va_outreach', 'va_manager')
            )
          )
        )
    )
  );

drop policy if exists "oqr_insert" on public.onboarding_quiz_results;
create policy "oqr_insert"
  on public.onboarding_quiz_results for insert
  with check (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

-- ---------------------------------------------------------------------------
-- 7) ai_action_log — every AI Command Center action
-- ---------------------------------------------------------------------------
create table if not exists public.ai_action_log (
  id uuid primary key default gen_random_uuid(),
  triggered_by uuid not null references public.profiles (id),
  action_type text not null,
  action_payload jsonb default '{}'::jsonb,
  result text,
  created_at timestamptz not null default now()
);

create index if not exists idx_ai_action_log_by on public.ai_action_log (triggered_by);
create index if not exists idx_ai_action_log_created on public.ai_action_log (created_at desc);

alter table public.ai_action_log enable row level security;

drop policy if exists "aal_select" on public.ai_action_log;
create policy "aal_select"
  on public.ai_action_log for select
  using (
    triggered_by = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "aal_insert" on public.ai_action_log;
create policy "aal_insert"
  on public.ai_action_log for insert
  with check (
    triggered_by = (select auth.uid())
    or public.crm_is_privileged()
  );

-- ---------------------------------------------------------------------------
-- 8) scheduled_ai_actions — cron-executed AI actions
-- ---------------------------------------------------------------------------
create table if not exists public.scheduled_ai_actions (
  id uuid primary key default gen_random_uuid(),
  triggered_by uuid not null references public.profiles (id),
  action_type text not null,
  action_payload jsonb default '{}'::jsonb,
  scheduled_for timestamptz not null,
  executed boolean not null default false,
  executed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_sched_ai_pending on public.scheduled_ai_actions (executed, scheduled_for);

alter table public.scheduled_ai_actions enable row level security;

drop policy if exists "saa_select" on public.scheduled_ai_actions;
create policy "saa_select"
  on public.scheduled_ai_actions for select
  using (
    triggered_by = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "saa_insert" on public.scheduled_ai_actions;
create policy "saa_insert"
  on public.scheduled_ai_actions for insert
  with check (
    triggered_by = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "saa_update" on public.scheduled_ai_actions;
create policy "saa_update"
  on public.scheduled_ai_actions for update
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 9) ai_chat_conversations — persisted AI Command Center conversations
-- ---------------------------------------------------------------------------
create table if not exists public.ai_chat_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  title text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_ai_chat_conv_user on public.ai_chat_conversations (user_id);

alter table public.ai_chat_conversations enable row level security;

drop policy if exists "acc_select" on public.ai_chat_conversations;
create policy "acc_select"
  on public.ai_chat_conversations for select
  using (user_id = (select auth.uid()));

drop policy if exists "acc_insert" on public.ai_chat_conversations;
create policy "acc_insert"
  on public.ai_chat_conversations for insert
  with check (user_id = (select auth.uid()));

drop policy if exists "acc_update" on public.ai_chat_conversations;
create policy "acc_update"
  on public.ai_chat_conversations for update
  using (user_id = (select auth.uid()));

drop policy if exists "acc_delete" on public.ai_chat_conversations;
create policy "acc_delete"
  on public.ai_chat_conversations for delete
  using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- 10) ai_chat_messages — individual messages in conversations
-- ---------------------------------------------------------------------------
create table if not exists public.ai_chat_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.ai_chat_conversations (id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system', 'function')),
  content text not null default '',
  function_name text,
  function_args jsonb,
  function_result text,
  created_at timestamptz not null default now()
);

create index if not exists idx_ai_chat_msgs_conv on public.ai_chat_messages (conversation_id, created_at);

alter table public.ai_chat_messages enable row level security;

drop policy if exists "acm_select" on public.ai_chat_messages;
create policy "acm_select"
  on public.ai_chat_messages for select
  using (
    exists (
      select 1 from public.ai_chat_conversations c
      where c.id = ai_chat_messages.conversation_id
        and c.user_id = (select auth.uid())
    )
  );

drop policy if exists "acm_insert" on public.ai_chat_messages;
create policy "acm_insert"
  on public.ai_chat_messages for insert
  with check (
    exists (
      select 1 from public.ai_chat_conversations c
      where c.id = conversation_id
        and c.user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- 11) Storage bucket for onboarding documents (gov IDs, signed PDFs)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'onboarding-documents',
  'onboarding-documents',
  false,
  52428800,
  array['application/pdf', 'image/png', 'image/jpeg']::text[]
)
on conflict (id) do nothing;

-- Storage policies: user can upload to their own folder; privileged can read all
drop policy if exists "onb_docs_upload" on storage.objects;
create policy "onb_docs_upload"
  on storage.objects for insert
  with check (
    bucket_id = 'onboarding-documents'
    and (
      (storage.foldername(name))[1] = (select auth.uid())::text
      or public.crm_is_privileged()
    )
  );

drop policy if exists "onb_docs_select" on storage.objects;
create policy "onb_docs_select"
  on storage.objects for select
  using (
    bucket_id = 'onboarding-documents'
    and (
      (storage.foldername(name))[1] = (select auth.uid())::text
      or public.crm_is_privileged()
      or exists (
        select 1 from public.profiles me
        where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      )
    )
  );

-- ---------------------------------------------------------------------------
-- 12) Add onboarding_status to profiles for middleware redirect
-- ---------------------------------------------------------------------------
alter table public.profiles
  add column if not exists onboarding_status text
    default null;

comment on column public.profiles.onboarding_status is
  'AI onboarding portal status: in_progress | pending_review | approved | rejected. NULL = no onboarding needed (CEO, legacy).';

-- Update status check to include onboarding-related statuses
alter table public.profiles drop constraint if exists profiles_status_check;
alter table public.profiles
  add constraint profiles_status_check
  check (status in ('active', 'at_risk', 'inactive', 'invited', 'onboarding'));

-- >>> SOURCE: 20260427000001_aria_pipeline_tables.sql <<<
-- ARIA Phase 1 — Outbound Pipeline tables + rename existing AI tables
-- =========================================================================

-- ---------------------------------------------------------------------------
-- 1) aria_conversations — rename from ai_chat_conversations
-- ---------------------------------------------------------------------------
alter table if exists public.ai_chat_conversations rename to aria_conversations;

-- Update indexes
alter index if exists idx_ai_chat_conv_user rename to idx_aria_conversations_user;

-- Update RLS policies
alter policy "acc_select" on public.aria_conversations rename to "aria_conv_select";
alter policy "acc_insert" on public.aria_conversations rename to "aria_conv_insert";
alter policy "acc_update" on public.aria_conversations rename to "aria_conv_update";
alter policy "acc_delete" on public.aria_conversations rename to "aria_conv_delete";

-- ---------------------------------------------------------------------------
-- 2) aria_messages — rename from ai_chat_messages
-- ---------------------------------------------------------------------------
alter table if exists public.ai_chat_messages rename to aria_messages;

-- Add new columns for function results as jsonb
alter table public.aria_messages
  add column if not exists function_result_json jsonb;

-- Update indexes
alter index if exists idx_ai_chat_msgs_conv rename to idx_aria_messages_conv;

-- Update RLS policies
alter policy "acm_select" on public.aria_messages rename to "aria_msg_select";
alter policy "acm_insert" on public.aria_messages rename to "aria_msg_insert";

-- ---------------------------------------------------------------------------
-- 3) aria_action_log — rename from ai_action_log
-- ---------------------------------------------------------------------------
alter table if exists public.ai_action_log rename to aria_action_log;

-- Add new columns
alter table public.aria_action_log
  add column if not exists conversation_id uuid references public.aria_conversations (id),
  add column if not exists required_confirmation boolean not null default false,
  add column if not exists confirmed_at timestamptz;

-- Rename result column to action_result
alter table public.aria_action_log rename column result to action_result;

-- Update indexes
alter index if exists idx_ai_action_log_by rename to idx_aria_action_log_by;
alter index if exists idx_ai_action_log_created rename to idx_aria_action_log_created;

-- Update RLS policies
alter policy "aal_select" on public.aria_action_log rename to "aria_al_select";
alter policy "aal_insert" on public.aria_action_log rename to "aria_al_insert";

-- ---------------------------------------------------------------------------
-- 4) aria_scheduled_actions — rename from scheduled_ai_actions
-- ---------------------------------------------------------------------------
alter table if exists public.scheduled_ai_actions rename to aria_scheduled_actions;

-- Update indexes
alter index if exists idx_sched_ai_pending rename to idx_aria_sched_pending;

-- Update RLS policies
alter policy "saa_select" on public.aria_scheduled_actions rename to "aria_sa_select";
alter policy "saa_insert" on public.aria_scheduled_actions rename to "aria_sa_insert";
alter policy "saa_update" on public.aria_scheduled_actions rename to "aria_sa_update";

-- ---------------------------------------------------------------------------
-- 5) aria_proactive_briefings — new table
-- ---------------------------------------------------------------------------
create table if not exists public.aria_proactive_briefings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  briefing_date date not null,
  content text not null default '',
  read boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_aria_briefings_user on public.aria_proactive_briefings (user_id, briefing_date desc);

alter table public.aria_proactive_briefings enable row level security;

drop policy if exists "aria_brief_select" on public.aria_proactive_briefings;
create policy "aria_brief_select"
  on public.aria_proactive_briefings for select
  using (user_id = (select auth.uid()) or public.crm_is_privileged());

drop policy if exists "aria_brief_insert" on public.aria_proactive_briefings;
create policy "aria_brief_insert"
  on public.aria_proactive_briefings for insert
  with check (public.crm_is_privileged());

drop policy if exists "aria_brief_update" on public.aria_proactive_briefings;
create policy "aria_brief_update"
  on public.aria_proactive_briefings for update
  using (user_id = (select auth.uid()) or public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 6) aria_user_patterns — new table
-- ---------------------------------------------------------------------------
create table if not exists public.aria_user_patterns (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  pattern_key text not null,
  pattern_value jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique (user_id, pattern_key)
);

alter table public.aria_user_patterns enable row level security;

drop policy if exists "aria_up_select" on public.aria_user_patterns;
create policy "aria_up_select"
  on public.aria_user_patterns for select
  using (user_id = (select auth.uid()) or public.crm_is_privileged());

drop policy if exists "aria_up_upsert" on public.aria_user_patterns;
create policy "aria_up_upsert"
  on public.aria_user_patterns for insert
  with check (public.crm_is_privileged());

drop policy if exists "aria_up_update" on public.aria_user_patterns;
create policy "aria_up_update"
  on public.aria_user_patterns for update
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 7) aria_client_health_scores — new table
-- ---------------------------------------------------------------------------
create table if not exists public.aria_client_health_scores (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  score int not null default 100,
  factors jsonb not null default '{}'::jsonb,
  at_risk boolean not null default false,
  updated_at timestamptz not null default now(),
  unique (client_id)
);

create index if not exists idx_aria_chs_at_risk on public.aria_client_health_scores (at_risk) where at_risk = true;

alter table public.aria_client_health_scores enable row level security;

drop policy if exists "aria_chs_select" on public.aria_client_health_scores;
create policy "aria_chs_select"
  on public.aria_client_health_scores for select
  using (public.crm_is_privileged());

drop policy if exists "aria_chs_insert" on public.aria_client_health_scores;
create policy "aria_chs_insert"
  on public.aria_client_health_scores for insert
  with check (public.crm_is_privileged());

drop policy if exists "aria_chs_update" on public.aria_client_health_scores;
create policy "aria_chs_update"
  on public.aria_client_health_scores for update
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 8) aria_pipeline_runs — tracks each outbound pipeline execution
-- ---------------------------------------------------------------------------
create table if not exists public.aria_pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  triggered_by uuid not null references public.profiles (id),
  vertical text not null check (vertical in ('dental', 'legal', 'accounting')),
  location text not null,
  batch_size int not null default 50,
  leads_pulled int not null default 0,
  leads_enriched int not null default 0,
  leads_verified int not null default 0,
  leads_scanned int not null default 0,
  emails_generated int not null default 0,
  emails_sent int not null default 0,
  vulnerabilities_found int not null default 0,
  current_step text not null default 'apollo_pull',
  status text not null default 'running'
    check (status in ('running', 'paused', 'completed', 'failed')),
  error_message text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_aria_pr_triggered on public.aria_pipeline_runs (triggered_by);
create index if not exists idx_aria_pr_status on public.aria_pipeline_runs (status);

alter table public.aria_pipeline_runs enable row level security;

drop policy if exists "aria_pr_select" on public.aria_pipeline_runs;
create policy "aria_pr_select"
  on public.aria_pipeline_runs for select
  using (
    triggered_by = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "aria_pr_insert" on public.aria_pipeline_runs;
create policy "aria_pr_insert"
  on public.aria_pipeline_runs for insert
  with check (
    triggered_by = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "aria_pr_update" on public.aria_pipeline_runs;
create policy "aria_pr_update"
  on public.aria_pipeline_runs for update
  using (
    triggered_by = (select auth.uid())
    or public.crm_is_privileged()
  );

-- ---------------------------------------------------------------------------
-- 9) aria_pipeline_leads — individual leads within a pipeline run
-- ---------------------------------------------------------------------------
create table if not exists public.aria_pipeline_leads (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.aria_pipeline_runs (id) on delete cascade,
  company_name text,
  domain text,
  contact_name text,
  contact_email text,
  vertical text,
  apollo_data jsonb default '{}'::jsonb,
  clay_enrichment jsonb default '{}'::jsonb,
  zero_bounce_result jsonb default '{}'::jsonb,
  vulnerability_found text,
  email_sent boolean not null default false,
  email_subject text,
  email_content text,
  smartlead_campaign_id text,
  status text not null default 'pulled'
    check (status in ('pulled', 'enriched', 'verified', 'scanned', 'email_generated', 'sent', 'removed')),
  removed_reason text,
  created_at timestamptz not null default now()
);

create index if not exists idx_aria_pl_run on public.aria_pipeline_leads (run_id);
create index if not exists idx_aria_pl_status on public.aria_pipeline_leads (run_id, status);
create index if not exists idx_aria_pl_email on public.aria_pipeline_leads (contact_email);

alter table public.aria_pipeline_leads enable row level security;

drop policy if exists "aria_pl_select" on public.aria_pipeline_leads;
create policy "aria_pl_select"
  on public.aria_pipeline_leads for select
  using (
    exists (
      select 1 from public.aria_pipeline_runs r
      where r.id = aria_pipeline_leads.run_id
        and (r.triggered_by = (select auth.uid()) or public.crm_is_privileged())
    )
  );

drop policy if exists "aria_pl_insert" on public.aria_pipeline_leads;
create policy "aria_pl_insert"
  on public.aria_pipeline_leads for insert
  with check (public.crm_is_privileged());

drop policy if exists "aria_pl_update" on public.aria_pipeline_leads;
create policy "aria_pl_update"
  on public.aria_pipeline_leads for update
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 10) Storage bucket for ARIA generated documents (pipeline reports, etc.)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'aria-documents',
  'aria-documents',
  false,
  52428800,
  array['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']::text[]
)
on conflict (id) do nothing;

drop policy if exists "aria_docs_upload" on storage.objects;
create policy "aria_docs_upload"
  on storage.objects for insert
  with check (
    bucket_id = 'aria-documents'
    and public.crm_is_privileged()
  );

drop policy if exists "aria_docs_select" on storage.objects;
create policy "aria_docs_select"
  on storage.objects for select
  using (
    bucket_id = 'aria-documents'
    and (
      public.crm_is_privileged()
      or (storage.foldername(name))[1] = (select auth.uid())::text
    )
  );

-- >>> SOURCE: 20260428000001_aria_pgvector_memory.sql <<<
-- ARIA Phase 4 — Semantic memory via pgvector
-- =========================================================================
-- Enable pgvector extension (Supabase supports this natively)
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- 1) aria_memories — stores embedded CRM events for semantic retrieval
-- ---------------------------------------------------------------------------
create table if not exists public.aria_memories (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,          -- e.g. 'prospect_stage_change', 'client_onboarded', 'scan_completed', 'email_sent', 'deal_closed', 'note_added'
  event_id text,                     -- original record ID for dedup
  source_table text,                 -- which table the event came from
  actor_id uuid references public.profiles (id) on delete set null,
  subject_id text,                   -- prospect_id, client_id, etc.
  subject_type text,                 -- 'prospect', 'client', 'va', 'pipeline_run'
  summary text not null,             -- human-readable one-line summary
  detail text not null default '',   -- longer context for the embedding
  metadata jsonb not null default '{}'::jsonb,
  embedding extensions.vector(1536), -- OpenAI text-embedding-3-small dimension
  created_at timestamptz not null default now()
);

-- Indexes for efficient retrieval
create index if not exists idx_aria_mem_event_type on public.aria_memories (event_type);
create index if not exists idx_aria_mem_subject on public.aria_memories (subject_type, subject_id);
create index if not exists idx_aria_mem_created on public.aria_memories (created_at desc);
create index if not exists idx_aria_mem_event_id on public.aria_memories (event_id) where event_id is not null;

-- HNSW index for fast approximate nearest-neighbor search
create index if not exists idx_aria_mem_embedding on public.aria_memories
  using hnsw (embedding extensions.vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- RLS
alter table public.aria_memories enable row level security;

drop policy if exists "aria_mem_select" on public.aria_memories;
create policy "aria_mem_select"
  on public.aria_memories for select
  using (public.crm_is_privileged());

drop policy if exists "aria_mem_insert" on public.aria_memories;
create policy "aria_mem_insert"
  on public.aria_memories for insert
  with check (public.crm_is_privileged());

drop policy if exists "aria_mem_delete" on public.aria_memories;
create policy "aria_mem_delete"
  on public.aria_memories for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 2) RPC function for semantic search (cosine similarity)
-- ---------------------------------------------------------------------------
create or replace function public.aria_memory_search(
  query_embedding extensions.vector(1536),
  match_count int default 10,
  similarity_threshold float default 0.7,
  filter_event_type text default null,
  filter_subject_type text default null,
  filter_subject_id text default null
)
returns table (
  id uuid,
  event_type text,
  subject_type text,
  subject_id text,
  summary text,
  detail text,
  metadata jsonb,
  similarity float,
  created_at timestamptz
)
language plpgsql
security definer
as $$
begin
  return query
  select
    m.id,
    m.event_type,
    m.subject_type,
    m.subject_id,
    m.summary,
    m.detail,
    m.metadata,
    1 - (m.embedding <=> query_embedding) as similarity,
    m.created_at
  from public.aria_memories m
  where
    m.embedding is not null
    and 1 - (m.embedding <=> query_embedding) >= similarity_threshold
    and (filter_event_type is null or m.event_type = filter_event_type)
    and (filter_subject_type is null or m.subject_type = filter_subject_type)
    and (filter_subject_id is null or m.subject_id = filter_subject_id)
  order by m.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- >>> SOURCE: 20260430000001_aria_phases_8_19.sql <<<
-- ARIA Phases 8-19: Additional tables for voice, A/B testing, competitive intel,
-- playbooks, WhatsApp, API keys, webhooks, and training sessions.

-- ── Phase 10: A/B Experiments ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_ab_experiments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    variant_a jsonb NOT NULL DEFAULT '{}'::jsonb,
    variant_b jsonb NOT NULL DEFAULT '{}'::jsonb,
    campaign_id text,
    status text NOT NULL DEFAULT 'created',
    results jsonb,
    winner text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_ab_experiments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_ab_experiments" ON aria_ab_experiments;
CREATE POLICY "Service role full access on aria_ab_experiments"
    ON aria_ab_experiments FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Phase 11: Competitive Intelligence ────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_competitive_intel (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type text NOT NULL DEFAULT 'competitive_analysis',
    content jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_competitive_intel ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_competitive_intel" ON aria_competitive_intel;
CREATE POLICY "Service role full access on aria_competitive_intel"
    ON aria_competitive_intel FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Phase 14: Playbooks ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_playbooks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    content jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_playbooks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_playbooks" ON aria_playbooks;
CREATE POLICY "Service role full access on aria_playbooks"
    ON aria_playbooks FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Phase 17: API Keys ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    key_hash text NOT NULL UNIQUE,
    permissions jsonb NOT NULL DEFAULT '{}'::jsonb,
    rate_limit int NOT NULL DEFAULT 100,
    active boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES profiles(id),
    last_used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_api_keys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_api_keys" ON aria_api_keys;
CREATE POLICY "Service role full access on aria_api_keys"
    ON aria_api_keys FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Phase 17: Webhooks ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_webhooks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    url text NOT NULL,
    events jsonb NOT NULL DEFAULT '[]'::jsonb,
    signing_secret text,
    api_key_id uuid REFERENCES aria_api_keys(id) ON DELETE CASCADE,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_webhooks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_webhooks" ON aria_webhooks;
CREATE POLICY "Service role full access on aria_webhooks"
    ON aria_webhooks FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Phase 18: WhatsApp Messages ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_whatsapp_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    direction text NOT NULL,  -- 'inbound' or 'outbound'
    phone text NOT NULL,
    content text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_whatsapp_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_whatsapp_messages" ON aria_whatsapp_messages;
CREATE POLICY "Service role full access on aria_whatsapp_messages"
    ON aria_whatsapp_messages FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE TABLE IF NOT EXISTS aria_whatsapp_queue (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phone text NOT NULL,
    inbound_text text NOT NULL DEFAULT '',
    drafted_reply text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'pending',  -- pending, sent, rejected, failed
    sent_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_whatsapp_queue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_whatsapp_queue" ON aria_whatsapp_queue;
CREATE POLICY "Service role full access on aria_whatsapp_queue"
    ON aria_whatsapp_queue FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Phase 19: Training Sessions ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_training_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES profiles(id),
    scenario_type text NOT NULL,
    title text NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'active',  -- active, completed
    messages jsonb NOT NULL DEFAULT '[]'::jsonb,
    score int,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aria_training_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on aria_training_sessions" ON aria_training_sessions;
CREATE POLICY "Service role full access on aria_training_sessions"
    ON aria_training_sessions FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Indices ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_aria_ab_experiments_status ON aria_ab_experiments(status);
CREATE INDEX IF NOT EXISTS idx_aria_competitive_intel_created ON aria_competitive_intel(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aria_api_keys_hash ON aria_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_aria_webhooks_api_key ON aria_webhooks(api_key_id);
CREATE INDEX IF NOT EXISTS idx_aria_whatsapp_messages_phone ON aria_whatsapp_messages(phone);
CREATE INDEX IF NOT EXISTS idx_aria_whatsapp_queue_status ON aria_whatsapp_queue(status);
CREATE INDEX IF NOT EXISTS idx_aria_training_sessions_user ON aria_training_sessions(user_id);

-- >>> SOURCE: 20260501000001_unified_pipeline_rebuild.sql <<<
-- Unified Pipeline Rebuild: aria_lead_inventory, aria_domain_health, aria_inbound_replies, crm_settings keys
-- Replaces Charlotte + ARIA pipeline with nightly build + morning dispatch architecture

-- ============================================================================
-- 1. aria_lead_inventory — central lead storage for nightly pipeline
-- ============================================================================

do $etype$ begin
  create type aria_lead_email_finder as enum ('prospeo', 'apollo', 'pattern');
exception when duplicate_object then null; end $etype$;
do $etype$ begin
  create type aria_lead_zb_result as enum ('valid', 'catch_all', 'invalid', 'removed');
exception when duplicate_object then null; end $etype$;
do $etype$ begin
  create type aria_lead_status as enum (
    'pending',
    'verified',
    'scanned',
    'personalized',
    'ready',
    'dispatched',
    'suppressed'
  );
exception when duplicate_object then null; end $etype$;

CREATE TABLE IF NOT EXISTS aria_lead_inventory (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Discovery fields (Google Places)
  business_name   text NOT NULL,
  domain          text NOT NULL,
  address         text,
  city            text,
  province        text,
  vertical        text NOT NULL,  -- dental, legal, accounting
  google_rating   numeric(2,1),
  review_count    integer,
  google_place_id text,
  -- Contact fields (Prospeo / Apollo)
  contact_name    text,
  contact_email   text,
  contact_title   text,
  email_finder    aria_lead_email_finder,
  -- Verification
  zero_bounce_result aria_lead_zb_result,
  zero_bounce_data jsonb DEFAULT '{}'::jsonb,
  -- Scan results
  hawk_score      integer,
  vulnerability_found text,
  no_finding      boolean DEFAULT false,
  scan_data       jsonb DEFAULT '{}'::jsonb,
  -- Personalized email
  email_subject   text,
  email_body      text,
  -- Scoring
  lead_score      integer DEFAULT 0,
  -- Dispatch
  status          aria_lead_status DEFAULT 'pending',
  smartlead_campaign_id text,
  scheduled_send_at timestamptz,
  dispatched_at   timestamptz,
  -- Suppression tracking
  suppression_reason text,
  -- Metadata
  nightly_run_date date,
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

-- Indexes for common queries
create index if not exists idx_inventory_status on aria_lead_inventory(status);
create index if not exists idx_inventory_vertical_status on aria_lead_inventory(vertical, status);
create index if not exists idx_inventory_domain on aria_lead_inventory(domain);
create index if not exists idx_inventory_email on aria_lead_inventory(contact_email);
create index if not exists idx_inventory_run_date on aria_lead_inventory(nightly_run_date);
create index if not exists idx_inventory_lead_score on aria_lead_inventory(lead_score desc);
create unique index if not exists idx_inventory_domain_email_uniq on aria_lead_inventory(domain, contact_email)
  where contact_email is not null;

-- RLS
alter table aria_lead_inventory enable row level security;
drop policy if exists "service_role_all_inventory" on aria_lead_inventory;
create policy "service_role_all_inventory" on aria_lead_inventory
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- ============================================================================
-- 2. aria_domain_health — inbox health monitoring per sending domain
-- ============================================================================

CREATE TABLE IF NOT EXISTS aria_domain_health (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  domain          text NOT NULL,
  -- Metrics (updated by inbox health cron)
  emails_sent_total     integer DEFAULT 0,
  emails_sent_7d        integer DEFAULT 0,
  bounces_7d            integer DEFAULT 0,
  spam_complaints_7d    integer DEFAULT 0,
  replies_7d            integer DEFAULT 0,
  bounce_rate_7d        numeric(5,4) DEFAULT 0,
  spam_rate_7d          numeric(5,4) DEFAULT 0,
  reply_rate_7d         numeric(5,4) DEFAULT 0,
  -- Blacklist monitoring
  blacklisted           boolean DEFAULT false,
  blacklist_entries     jsonb DEFAULT '[]'::jsonb,
  last_blacklist_check  timestamptz,
  -- Status
  health_status   text DEFAULT 'healthy',  -- healthy, warning, paused
  paused_at       timestamptz,
  pause_reason    text,
  -- Metadata
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

create unique index if not exists idx_domain_health_domain on aria_domain_health(domain);
create index if not exists idx_domain_health_status on aria_domain_health(health_status);

alter table aria_domain_health enable row level security;
drop policy if exists "service_role_all_domain_health" on aria_domain_health;
create policy "service_role_all_domain_health" on aria_domain_health
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- ============================================================================
-- 3. aria_inbound_replies — Smartlead webhook reply tracking
-- ============================================================================

do $etype$ begin
  create type aria_reply_sentiment as enum (
    'positive',
    'objection',
    'not_interested',
    'unsubscribe',
    'out_of_office',
    'question',
    'other'
  );
exception when duplicate_object then null; end $etype$;

do $etype$ begin
  create type aria_reply_status as enum (
    'pending',
    'classified',
    'approved',
    'sent',
    'rejected',
    'auto_handled'
  );
exception when duplicate_object then null; end $etype$;

CREATE TABLE IF NOT EXISTS aria_inbound_replies (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Source
  smartlead_lead_id text,
  smartlead_campaign_id text,
  prospect_email    text NOT NULL,
  prospect_name     text,
  prospect_domain   text,
  -- Reply content
  reply_subject     text,
  reply_body        text NOT NULL,
  reply_received_at timestamptz DEFAULT now(),
  -- ARIA classification
  sentiment         aria_reply_sentiment,
  confidence_score  numeric(3,2),
  classification_reasoning text,
  -- ARIA drafted response
  drafted_response_subject text,
  drafted_response_body text,
  -- Status
  status            aria_reply_status DEFAULT 'pending',
  approved_by       uuid,
  approved_at       timestamptz,
  sent_at           timestamptz,
  -- Link to inventory
  inventory_lead_id uuid REFERENCES aria_lead_inventory(id),
  -- Metadata
  webhook_payload   jsonb DEFAULT '{}'::jsonb,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now()
);

create index if not exists idx_replies_status on aria_inbound_replies(status);
create index if not exists idx_replies_sentiment on aria_inbound_replies(sentiment);
create index if not exists idx_replies_email on aria_inbound_replies(prospect_email);
create index if not exists idx_replies_received on aria_inbound_replies(reply_received_at desc);

alter table aria_inbound_replies enable row level security;
drop policy if exists "service_role_all_replies" on aria_inbound_replies;
create policy "service_role_all_replies" on aria_inbound_replies
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- ============================================================================
-- 4. crm_settings — new configuration keys for unified pipeline
-- ============================================================================

INSERT INTO crm_settings (key, value) VALUES
  ('smartlead_campaign_id_dental', ''),
  ('smartlead_campaign_id_legal', ''),
  ('smartlead_campaign_id_accounting', ''),
  ('daily_send_limit', '3000'),
  ('per_inbox_daily_cap', '50'),
  ('pipeline_nightly_enabled', 'true'),
  ('pipeline_dispatch_enabled', 'true'),
  ('google_places_cities', '["Toronto","Vancouver","Calgary","Edmonton","Ottawa","Montreal","Winnipeg","Halifax","Quebec City","Saskatoon","Regina","Victoria","Kelowna","London","Hamilton","Waterloo","Mississauga","Brampton"]')
ON CONFLICT (key) DO NOTHING;

-- >>> SOURCE: 20260502000001_prospects_pipeline_progressive.sql <<<
-- Progressive ARIA pipeline visibility on CRM prospects (no drops of existing columns)

alter table public.prospects
  add column if not exists address text,
  add column if not exists province text,
  add column if not exists pipeline_status text,
  add column if not exists email_finder text,
  add column if not exists zero_bounce_result text,
  add column if not exists vulnerability_found text,
  add column if not exists vulnerability_type text,
  add column if not exists email_subject text,
  add column if not exists email_body text,
  add column if not exists smartlead_campaign_id text,
  add column if not exists dispatched_at timestamptz,
  add column if not exists lead_score integer,
  add column if not exists google_rating double precision,
  add column if not exists review_count integer,
  add column if not exists pipeline_run_id uuid references public.aria_pipeline_runs (id) on delete set null;

comment on column public.prospects.pipeline_status is 'ARIA outbound pipeline stage: discovered, enriched, verified, scanned, ready, contacted, suppressed';

alter table public.prospects drop constraint if exists prospects_source_check;
alter table public.prospects add constraint prospects_source_check
  check (source in (
    'charlotte',
    'manual',
    'inbound',
    'homepage_scanner',
    'aria_nightly',
    'aria_chat'
  ));

create index if not exists idx_prospects_pipeline_status
  on public.prospects (pipeline_status)
  where pipeline_status is not null;

create index if not exists idx_prospects_pipeline_run
  on public.prospects (pipeline_run_id)
  where pipeline_run_id is not null;

-- >>> SOURCE: 20260503000001_guardian_client_risk.sql <<<
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

-- >>> SOURCE: 20260504000001_schema_compat_code_alignment.sql <<<
-- Code/schema alignment — objects referenced by Python that were missing or misnamed.
-- Safe to re-run (idempotent).

-- ---------------------------------------------------------------------------
-- crm_notifications — aria_inbox_health.py POSTs role-scoped alerts here
-- (distinct from public.notifications which is user_id keyed).
-- ---------------------------------------------------------------------------
create table if not exists public.crm_notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_role text not null,
  title text not null,
  body text not null default '',
  category text,
  read boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_crm_notifications_role_unread
  on public.crm_notifications (recipient_role, read, created_at desc);

alter table public.crm_notifications enable row level security;

drop policy if exists "crm_notifications_service_all" on public.crm_notifications;
create policy "crm_notifications_service_all"
  on public.crm_notifications for all
  to public
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "crm_notifications_select_privileged" on public.crm_notifications;
create policy "crm_notifications_select_privileged"
  on public.crm_notifications for select
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- prospect_scans view — aria_memory.py reads /rest/v1/prospect_scans
-- Maps to crm_prospect_scans + prospect domain; severity columns default 0.
-- ---------------------------------------------------------------------------
create or replace view public.prospect_scans as
select
  s.id,
  s.prospect_id,
  coalesce(p.domain, '') as domain,
  coalesce(s.hawk_score, 0) as hawk_score,
  coalesce((s.findings ->> 'critical')::int, 0) as critical,
  coalesce((s.findings ->> 'high')::int, 0) as high,
  coalesce((s.findings ->> 'medium')::int, 0) as medium,
  coalesce((s.findings ->> 'low')::int, 0) as low,
  s.created_at
from public.crm_prospect_scans s
left join public.prospects p on p.id = s.prospect_id;

grant select on public.prospect_scans to authenticated;
grant select on public.prospect_scans to service_role;
