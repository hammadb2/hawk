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
