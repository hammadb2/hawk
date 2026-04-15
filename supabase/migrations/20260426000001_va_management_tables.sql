-- VA Management System — tables, enums, RLS, indexes
-- Depends on: 20260425000001_profiles_role_type_va_rls.sql (role_type column on profiles)

-- ---------------------------------------------------------------------------
-- 1) va_profiles — each VA team member
-- ---------------------------------------------------------------------------
create table if not exists public.va_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  full_name text not null,
  email text not null,
  role text not null default 'reply_book'
    check (role in ('list_qa', 'reply_book')),
  status text not null default 'active'
    check (status in ('active', 'pip', 'inactive')),
  start_date date not null default current_date,
  created_at timestamptz not null default now()
);

create index if not exists idx_va_profiles_user on public.va_profiles (user_id);
create index if not exists idx_va_profiles_status on public.va_profiles (status);

alter table public.va_profiles enable row level security;

-- CEO / HoS full access
create policy "va_profiles_select_privileged" on public.va_profiles for select
  using (public.crm_is_privileged());

create policy "va_profiles_insert_privileged" on public.va_profiles for insert
  with check (public.crm_is_privileged());

create policy "va_profiles_update_privileged" on public.va_profiles for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

create policy "va_profiles_delete_privileged" on public.va_profiles for delete
  using (public.crm_is_privileged());

-- VA manager can read + update VA profiles
create policy "va_profiles_select_va_manager" on public.va_profiles for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "va_profiles_insert_va_manager" on public.va_profiles for insert
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "va_profiles_update_va_manager" on public.va_profiles for update
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

-- VA can see own profile
create policy "va_profiles_select_own" on public.va_profiles for select
  using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- 2) va_daily_reports — daily input from each VA
-- ---------------------------------------------------------------------------
create table if not exists public.va_daily_reports (
  id uuid primary key default gen_random_uuid(),
  va_id uuid not null references public.va_profiles(id) on delete cascade,
  report_date date not null default current_date,
  emails_sent int not null default 0,
  replies_received int not null default 0,
  positive_replies int not null default 0,
  calls_booked int not null default 0,
  no_shows int not null default 0,
  domains_scanned int not null default 0,
  blockers text,
  submitted_at timestamptz not null default now()
);

create index if not exists idx_va_daily_reports_va on public.va_daily_reports (va_id);
create index if not exists idx_va_daily_reports_date on public.va_daily_reports (report_date);
create unique index if not exists idx_va_daily_reports_va_date on public.va_daily_reports (va_id, report_date);

alter table public.va_daily_reports enable row level security;

create policy "va_daily_reports_select_privileged" on public.va_daily_reports for select
  using (public.crm_is_privileged());

create policy "va_daily_reports_select_va_manager" on public.va_daily_reports for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

-- VA can see + insert own reports
create policy "va_daily_reports_select_own" on public.va_daily_reports for select
  using (
    exists (
      select 1 from public.va_profiles vp
      where vp.id = va_daily_reports.va_id and vp.user_id = (select auth.uid())
    )
  );

create policy "va_daily_reports_insert_own" on public.va_daily_reports for insert
  with check (
    exists (
      select 1 from public.va_profiles vp
      where vp.id = va_id and vp.user_id = (select auth.uid())
    )
  );

create policy "va_daily_reports_update_own" on public.va_daily_reports for update
  using (
    exists (
      select 1 from public.va_profiles vp
      where vp.id = va_daily_reports.va_id and vp.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.va_profiles vp
      where vp.id = va_id and vp.user_id = (select auth.uid())
    )
  );

-- Privileged can also insert/update (for crons, admin)
create policy "va_daily_reports_insert_privileged" on public.va_daily_reports for insert
  with check (public.crm_is_privileged());

create policy "va_daily_reports_update_privileged" on public.va_daily_reports for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 3) va_scores — weekly scoring per VA
-- ---------------------------------------------------------------------------
create table if not exists public.va_scores (
  id uuid primary key default gen_random_uuid(),
  va_id uuid not null references public.va_profiles(id) on delete cascade,
  week_start date not null,
  output_score int not null default 0,
  accuracy_score int not null default 0,
  reply_quality_score int not null default 0,
  booking_score int not null default 0,
  total_score int not null default 0,
  standing text not null default 'green'
    check (standing in ('green', 'yellow', 'red')),
  created_at timestamptz not null default now()
);

create index if not exists idx_va_scores_va on public.va_scores (va_id);
create index if not exists idx_va_scores_week on public.va_scores (week_start);
create unique index if not exists idx_va_scores_va_week on public.va_scores (va_id, week_start);

alter table public.va_scores enable row level security;

create policy "va_scores_select_privileged" on public.va_scores for select
  using (public.crm_is_privileged());

create policy "va_scores_select_va_manager" on public.va_scores for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "va_scores_select_own" on public.va_scores for select
  using (
    exists (
      select 1 from public.va_profiles vp
      where vp.id = va_scores.va_id and vp.user_id = (select auth.uid())
    )
  );

-- Insert/update only by privileged (cron writes scores)
create policy "va_scores_insert_privileged" on public.va_scores for insert
  with check (public.crm_is_privileged());

create policy "va_scores_update_privileged" on public.va_scores for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 4) va_coaching_notes — manager notes on VA performance
-- ---------------------------------------------------------------------------
create table if not exists public.va_coaching_notes (
  id uuid primary key default gen_random_uuid(),
  va_id uuid not null references public.va_profiles(id) on delete cascade,
  manager_id uuid not null references public.profiles(id) on delete set null,
  note text not null,
  type text not null default 'coaching'
    check (type in ('coaching', 'pip', 'commendation')),
  created_at timestamptz not null default now()
);

create index if not exists idx_va_coaching_notes_va on public.va_coaching_notes (va_id);

alter table public.va_coaching_notes enable row level security;

create policy "va_coaching_notes_select_privileged" on public.va_coaching_notes for select
  using (public.crm_is_privileged());

create policy "va_coaching_notes_select_va_manager" on public.va_coaching_notes for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "va_coaching_notes_insert_privileged" on public.va_coaching_notes for insert
  with check (public.crm_is_privileged());

create policy "va_coaching_notes_insert_va_manager" on public.va_coaching_notes for insert
  with check (
    manager_id = (select auth.uid())
    and exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

-- VA can see coaching notes about themselves
create policy "va_coaching_notes_select_own" on public.va_coaching_notes for select
  using (
    exists (
      select 1 from public.va_profiles vp
      where vp.id = va_coaching_notes.va_id and vp.user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- 5) ab_tests — A/B test log for email campaigns
-- ---------------------------------------------------------------------------
create table if not exists public.ab_tests (
  id uuid primary key default gen_random_uuid(),
  subject_line text not null,
  email_body text not null default '',
  vertical text not null default 'dental'
    check (vertical in ('dental', 'legal', 'accounting')),
  sends int not null default 0,
  open_rate float not null default 0,
  reply_rate float not null default 0,
  book_rate float not null default 0,
  winner boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_ab_tests_vertical on public.ab_tests (vertical);

alter table public.ab_tests enable row level security;

create policy "ab_tests_select_privileged" on public.ab_tests for select
  using (public.crm_is_privileged());

create policy "ab_tests_select_va_manager" on public.ab_tests for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "ab_tests_insert_privileged" on public.ab_tests for insert
  with check (public.crm_is_privileged());

create policy "ab_tests_insert_va_manager" on public.ab_tests for insert
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "ab_tests_update_privileged" on public.ab_tests for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

create policy "ab_tests_update_va_manager" on public.ab_tests for update
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "ab_tests_delete_privileged" on public.ab_tests for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 6) objections — objection bank
-- ---------------------------------------------------------------------------
create table if not exists public.objections (
  id uuid primary key default gen_random_uuid(),
  objection_text text not null,
  response_used text not null default '',
  outcome text not null default 'not_interested'
    check (outcome in ('booked', 'warm', 'not_interested')),
  vertical text not null default 'dental'
    check (vertical in ('dental', 'legal', 'accounting')),
  logged_by uuid references public.va_profiles(id) on delete set null,
  created_at timestamptz not null default now()
);

create index if not exists idx_objections_vertical on public.objections (vertical);
create index if not exists idx_objections_outcome on public.objections (outcome);

alter table public.objections enable row level security;

create policy "objections_select_privileged" on public.objections for select
  using (public.crm_is_privileged());

create policy "objections_select_va_manager" on public.objections for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "objections_insert_privileged" on public.objections for insert
  with check (public.crm_is_privileged());

create policy "objections_insert_va_manager" on public.objections for insert
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "objections_update_privileged" on public.objections for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

create policy "objections_delete_privileged" on public.objections for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 7) domain_health — domain warming / health tracking
-- ---------------------------------------------------------------------------
create table if not exists public.domain_health (
  id uuid primary key default gen_random_uuid(),
  domain text not null,
  warmup_day int not null default 0,
  daily_sends int not null default 0,
  bounce_rate float not null default 0,
  status text not null default 'warming'
    check (status in ('active', 'warming', 'paused', 'flagged')),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_domain_health_domain on public.domain_health (domain);

alter table public.domain_health enable row level security;

create policy "domain_health_select_privileged" on public.domain_health for select
  using (public.crm_is_privileged());

create policy "domain_health_select_va_manager" on public.domain_health for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "domain_health_insert_privileged" on public.domain_health for insert
  with check (public.crm_is_privileged());

create policy "domain_health_insert_va_manager" on public.domain_health for insert
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "domain_health_update_privileged" on public.domain_health for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

create policy "domain_health_update_va_manager" on public.domain_health for update
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "domain_health_delete_privileged" on public.domain_health for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 8) campaign_preflight — pre-send checklist
-- ---------------------------------------------------------------------------
create table if not exists public.campaign_preflight (
  id uuid primary key default gen_random_uuid(),
  check_date date not null default current_date,
  checks jsonb not null default '{}',
  completed_by uuid references public.profiles(id) on delete set null,
  go_status boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_campaign_preflight_date on public.campaign_preflight (check_date);

alter table public.campaign_preflight enable row level security;

create policy "campaign_preflight_select_privileged" on public.campaign_preflight for select
  using (public.crm_is_privileged());

create policy "campaign_preflight_select_va_manager" on public.campaign_preflight for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "campaign_preflight_insert_privileged" on public.campaign_preflight for insert
  with check (public.crm_is_privileged());

create policy "campaign_preflight_insert_va_manager" on public.campaign_preflight for insert
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "campaign_preflight_update_privileged" on public.campaign_preflight for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

create policy "campaign_preflight_update_va_manager" on public.campaign_preflight for update
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

-- ---------------------------------------------------------------------------
-- 9) va_alerts — automated alerts for VA ops
-- ---------------------------------------------------------------------------
create table if not exists public.va_alerts (
  id uuid primary key default gen_random_uuid(),
  alert_type text not null
    check (alert_type in (
      'low_calls', 'high_bounce', 'low_reply_rate',
      'missed_input', 'red_score'
    )),
  va_id uuid references public.va_profiles(id) on delete cascade,
  domain text,
  message text not null,
  acknowledged boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_va_alerts_type on public.va_alerts (alert_type);
create index if not exists idx_va_alerts_va on public.va_alerts (va_id);
create index if not exists idx_va_alerts_ack on public.va_alerts (acknowledged) where not acknowledged;

alter table public.va_alerts enable row level security;

create policy "va_alerts_select_privileged" on public.va_alerts for select
  using (public.crm_is_privileged());

create policy "va_alerts_select_va_manager" on public.va_alerts for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

create policy "va_alerts_insert_privileged" on public.va_alerts for insert
  with check (public.crm_is_privileged());

create policy "va_alerts_update_privileged" on public.va_alerts for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

create policy "va_alerts_update_va_manager" on public.va_alerts for update
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
  );

-- ---------------------------------------------------------------------------
-- Done — all VA management tables created with RLS
-- ---------------------------------------------------------------------------
