-- Apollo swap + VA manager system
--
-- * Adds contact_phone + contact_linkedin_url columns on prospects so the
--   Apollo enrichment payload can land alongside email/name/title.
-- * Extends pipeline_status CHECK to include `va_queue` for prospects routed
--   to the manual-outreach team after the 600/day automated cap is hit.
-- * Creates `va_assignments` (queue → assigned → outcome state machine) and
--   `va_outreach_log` (append-only audit trail of every VA touch).
-- * Seeds new crm_settings keys: apollo_daily_credit_cap, discovery_daily_target,
--   google_places_max_per_search (bumped 10 → 40), apollo_people_topup_enabled,
--   va_queue_enabled, va_daily_target_per_va.
-- * Drops legacy apify_enable_* keys (no longer consulted by the code).
--
-- Idempotent — safe to re-run.

-- ---------------------------------------------------------------------------
-- 1) Prospects: new contact_phone / contact_linkedin_url + va_queue status
-- ---------------------------------------------------------------------------
alter table public.prospects
  add column if not exists contact_phone text,
  add column if not exists contact_linkedin_url text;

alter table public.prospects drop constraint if exists prospects_pipeline_status_check;
alter table public.prospects
  add constraint prospects_pipeline_status_check
  check (pipeline_status in (
    'discovered', 'scanning', 'scanned', 'enriching', 'ready',
    'dispatched', 'va_queue', 'closed'
  ));

create index if not exists idx_prospects_pipeline_status_industry
  on public.prospects (pipeline_status, industry);

-- ---------------------------------------------------------------------------
-- 2) VA assignments — VA queue → assignment → outcome state machine
-- ---------------------------------------------------------------------------
create table if not exists public.va_assignments (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects(id) on delete cascade,
  assigned_va_id uuid references public.profiles(id) on delete set null,
  assigned_by uuid references public.profiles(id) on delete set null,
  assigned_at timestamptz not null default now(),
  status text not null default 'assigned'
    check (status in (
      'unassigned', 'assigned', 'in_progress',
      'reached_out', 'call_booked', 'no_answer',
      'not_interested', 'closed_lost', 'closed_won'
    )),
  notes text,
  last_activity_at timestamptz not null default now()
);

create unique index if not exists uq_va_assignments_prospect
  on public.va_assignments (prospect_id);

create index if not exists idx_va_assignments_va
  on public.va_assignments (assigned_va_id);

create index if not exists idx_va_assignments_status
  on public.va_assignments (status);

alter table public.va_assignments enable row level security;

drop policy if exists "va_assignments_select" on public.va_assignments;
create policy "va_assignments_select"
  on public.va_assignments for select
  using (
    public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type in ('va_manager', 'va_outreach')
    )
  );

drop policy if exists "va_assignments_insert" on public.va_assignments;
create policy "va_assignments_insert"
  on public.va_assignments for insert
  with check (
    public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type = 'va_manager'
    )
  );

drop policy if exists "va_assignments_update" on public.va_assignments;
create policy "va_assignments_update"
  on public.va_assignments for update
  using (
    public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type = 'va_manager'
    )
    or assigned_va_id = (select auth.uid())
  )
  with check (
    public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type = 'va_manager'
    )
    or assigned_va_id = (select auth.uid())
  );

drop policy if exists "va_assignments_delete" on public.va_assignments;
create policy "va_assignments_delete"
  on public.va_assignments for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 3) VA outreach log — append-only audit trail
-- ---------------------------------------------------------------------------
create table if not exists public.va_outreach_log (
  id uuid primary key default gen_random_uuid(),
  assignment_id uuid not null references public.va_assignments(id) on delete cascade,
  va_id uuid references public.profiles(id) on delete set null,
  channel text not null default 'email'
    check (channel in ('email', 'phone', 'linkedin', 'sms', 'other')),
  outcome text not null
    check (outcome in (
      'sent', 'bounce', 'reply', 'no_answer',
      'voicemail', 'call_booked', 'not_interested', 'note'
    )),
  notes text,
  logged_at timestamptz not null default now()
);

create index if not exists idx_va_outreach_log_assignment
  on public.va_outreach_log (assignment_id);

create index if not exists idx_va_outreach_log_va_day
  on public.va_outreach_log (va_id, (logged_at::date));

alter table public.va_outreach_log enable row level security;

drop policy if exists "va_outreach_log_select" on public.va_outreach_log;
create policy "va_outreach_log_select"
  on public.va_outreach_log for select
  using (
    public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type in ('va_manager', 'va_outreach')
    )
  );

drop policy if exists "va_outreach_log_insert" on public.va_outreach_log;
create policy "va_outreach_log_insert"
  on public.va_outreach_log for insert
  with check (
    public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type in ('va_manager', 'va_outreach')
    )
  );

-- ---------------------------------------------------------------------------
-- 4) crm_settings seed + cleanup
-- ---------------------------------------------------------------------------
insert into public.crm_settings(key, value, description)
values
  ('apollo_daily_credit_cap', '2500',
   'Daily Apollo enrichment credit cap (soft budget guard).'),
  ('apollo_credits_used_today', '0',
   'Running count of Apollo credits consumed today (reset at UTC midnight).'),
  ('apollo_credits_used_date', '',
   'UTC date that `apollo_credits_used_today` applies to.'),
  ('apollo_people_topup_enabled', 'true',
   'If true, top discovery up to `discovery_daily_target` via Apollo people search.'),
  ('discovery_daily_target', '2000',
   'Target number of raw leads discovered per day (Google Places + Apollo combined).'),
  ('google_places_max_per_search', '40',
   'Max businesses returned per (vertical, city) Google Places query.'),
  ('va_queue_enabled', 'true',
   'If true, route prospects past the 600/day dispatcher cap into the VA queue.'),
  ('va_daily_target_per_va', '60',
   'Target manual outreach count per VA per day (used for Team tab pacing).')
on conflict (key) do nothing;

-- Drop legacy Apify per-actor kill switches — actors 2/3/4 are gone.
delete from public.crm_settings
 where key in (
   'apify_enable_actor2_linkedin',
   'apify_enable_actor3_leads_finder',
   'apify_enable_actor4_website_crawl'
 );
