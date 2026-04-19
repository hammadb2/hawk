-- ARIA Phase 1 — Outbound Pipeline tables + rename existing AI tables
-- =========================================================================

-- ---------------------------------------------------------------------------
-- 1) aria_conversations — rename from ai_chat_conversations (idempotent)
-- ---------------------------------------------------------------------------
do $r1$ begin
  if to_regclass('public.ai_chat_conversations') is not null
     and to_regclass('public.aria_conversations') is null then
    alter table public.ai_chat_conversations rename to aria_conversations;
  end if;
end $r1$;

do $r1i$ begin
  if to_regclass('public.idx_ai_chat_conv_user') is not null
     and to_regclass('public.idx_aria_conversations_user') is null then
    alter index public.idx_ai_chat_conv_user rename to idx_aria_conversations_user;
  end if;
end $r1i$;

do $r1p$ begin
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_conversations' and policyname = 'acc_select'
  ) then
    alter policy "acc_select" on public.aria_conversations rename to "aria_conv_select";
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_conversations' and policyname = 'acc_insert'
  ) then
    alter policy "acc_insert" on public.aria_conversations rename to "aria_conv_insert";
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_conversations' and policyname = 'acc_update'
  ) then
    alter policy "acc_update" on public.aria_conversations rename to "aria_conv_update";
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_conversations' and policyname = 'acc_delete'
  ) then
    alter policy "acc_delete" on public.aria_conversations rename to "aria_conv_delete";
  end if;
end $r1p$;

-- ---------------------------------------------------------------------------
-- 2) aria_messages — rename from ai_chat_messages (idempotent)
-- ---------------------------------------------------------------------------
do $r2$ begin
  if to_regclass('public.ai_chat_messages') is not null
     and to_regclass('public.aria_messages') is null then
    alter table public.ai_chat_messages rename to aria_messages;
  end if;
end $r2$;

-- Add new columns for function results as jsonb
alter table if exists public.aria_messages
  add column if not exists function_result_json jsonb;

do $r2i$ begin
  if to_regclass('public.idx_ai_chat_msgs_conv') is not null
     and to_regclass('public.idx_aria_messages_conv') is null then
    alter index public.idx_ai_chat_msgs_conv rename to idx_aria_messages_conv;
  end if;
end $r2i$;

do $r2p$ begin
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_messages' and policyname = 'acm_select'
  ) then
    alter policy "acm_select" on public.aria_messages rename to "aria_msg_select";
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_messages' and policyname = 'acm_insert'
  ) then
    alter policy "acm_insert" on public.aria_messages rename to "aria_msg_insert";
  end if;
end $r2p$;

-- ---------------------------------------------------------------------------
-- 3) aria_action_log — rename from ai_action_log (idempotent)
-- ---------------------------------------------------------------------------
do $r3$ begin
  if to_regclass('public.ai_action_log') is not null
     and to_regclass('public.aria_action_log') is null then
    alter table public.ai_action_log rename to aria_action_log;
  end if;
end $r3$;

-- Add new columns
alter table if exists public.aria_action_log
  add column if not exists conversation_id uuid references public.aria_conversations (id),
  add column if not exists required_confirmation boolean not null default false,
  add column if not exists confirmed_at timestamptz;

do $r3c$ begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'aria_action_log' and column_name = 'result'
  ) then
    alter table public.aria_action_log rename column result to action_result;
  end if;
end $r3c$;

do $r3i$ begin
  if to_regclass('public.idx_ai_action_log_by') is not null
     and to_regclass('public.idx_aria_action_log_by') is null then
    alter index public.idx_ai_action_log_by rename to idx_aria_action_log_by;
  end if;
  if to_regclass('public.idx_ai_action_log_created') is not null
     and to_regclass('public.idx_aria_action_log_created') is null then
    alter index public.idx_ai_action_log_created rename to idx_aria_action_log_created;
  end if;
end $r3i$;

do $r3p$ begin
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_action_log' and policyname = 'aal_select'
  ) then
    alter policy "aal_select" on public.aria_action_log rename to "aria_al_select";
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_action_log' and policyname = 'aal_insert'
  ) then
    alter policy "aal_insert" on public.aria_action_log rename to "aria_al_insert";
  end if;
end $r3p$;

-- ---------------------------------------------------------------------------
-- 4) aria_scheduled_actions — rename from scheduled_ai_actions (idempotent)
-- ---------------------------------------------------------------------------
do $r4$ begin
  if to_regclass('public.scheduled_ai_actions') is not null
     and to_regclass('public.aria_scheduled_actions') is null then
    alter table public.scheduled_ai_actions rename to aria_scheduled_actions;
  end if;
end $r4$;

do $r4i$ begin
  if to_regclass('public.idx_sched_ai_pending') is not null
     and to_regclass('public.idx_aria_sched_pending') is null then
    alter index public.idx_sched_ai_pending rename to idx_aria_sched_pending;
  end if;
end $r4i$;

do $r4p$ begin
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_scheduled_actions' and policyname = 'saa_select'
  ) then
    alter policy "saa_select" on public.aria_scheduled_actions rename to "aria_sa_select";
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_scheduled_actions' and policyname = 'saa_insert'
  ) then
    alter policy "saa_insert" on public.aria_scheduled_actions rename to "aria_sa_insert";
  end if;
  if exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'aria_scheduled_actions' and policyname = 'saa_update'
  ) then
    alter policy "saa_update" on public.aria_scheduled_actions rename to "aria_sa_update";
  end if;
end $r4p$;

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
