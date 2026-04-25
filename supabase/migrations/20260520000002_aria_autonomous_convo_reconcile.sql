-- Reconcile aria autonomous-conversation schema in prod Supabase.
--
-- Background: PR #36 added the autonomous-reply / nurture-drip / scheduled-actions
-- machinery via migration 20260518000001_aria_autonomous_convo.sql. That migration
-- used `create table if not exists` against `aria_scheduled_actions`, which already
-- existed in prod (renamed from `scheduled_ai_actions` back in 20260427000001) with
-- a totally different column set. Result: no migration drift detection, but every
-- field in services/aria_scheduled_actions.py (`prospect_id`, `due_at`, `status`,
-- `payload`, `attempts`, …) referred to columns that don't exist. Same with the
-- new aria_inbound_replies extension columns and the prospects nurture columns.
--
-- aria_scheduled_actions had 0 rows in prod at reconcile time, so this migration
-- drops & recreates it with the schema PR #36 expects. The other deltas are
-- additive (`add column if not exists`), zero-risk.
--
-- Idempotent — safe to re-run.

-- ---------------------------------------------------------------------------
-- 1) prospects — nurture sequence bookkeeping + Apollo enrichment title.
-- ---------------------------------------------------------------------------
alter table public.prospects
  add column if not exists contact_title text,
  add column if not exists last_auto_reply_at timestamptz,
  add column if not exists nurture_started_at timestamptz,
  add column if not exists nurture_stopped_at timestamptz,
  add column if not exists nurture_stopped_reason text;


-- ---------------------------------------------------------------------------
-- 2) aria_inbound_replies — autonomous-handle telemetry.
-- ---------------------------------------------------------------------------
alter table public.aria_inbound_replies
  add column if not exists auto_sent_at timestamptz,
  add column if not exists auto_sent_mailbox_id uuid references public.crm_mailboxes(id) on delete set null,
  add column if not exists auto_sent_message_id text,
  add column if not exists checkpoint_reason text,
  add column if not exists objection_playbook text,
  add column if not exists knowledge_base_snippets_used integer not null default 0;

create index if not exists idx_aria_inbound_replies_auto_sent_at
  on public.aria_inbound_replies (auto_sent_at desc)
  where auto_sent_at is not null;


-- ---------------------------------------------------------------------------
-- 3) aria_scheduled_actions — drop & recreate to PR #36 schema.
--
-- Guarded: only drops when the existing table has zero rows AND is missing the
-- new schema (no `due_at` column). Otherwise this migration is a no-op for the
-- table.
-- ---------------------------------------------------------------------------
do $rebuild_scheduled$
declare
  has_table boolean;
  has_due_at boolean;
  row_count bigint;
begin
  has_table := to_regclass('public.aria_scheduled_actions') is not null;
  if has_table then
    select exists (
      select 1 from information_schema.columns
      where table_schema = 'public'
        and table_name = 'aria_scheduled_actions'
        and column_name = 'due_at'
    ) into has_due_at;
    if not has_due_at then
      execute 'select count(*) from public.aria_scheduled_actions' into row_count;
      if row_count = 0 then
        drop table public.aria_scheduled_actions cascade;
        has_table := false;
      else
        raise notice 'aria_scheduled_actions has % rows with legacy schema; refusing to drop', row_count;
      end if;
    end if;
  end if;

  if not has_table then
    create table public.aria_scheduled_actions (
      id uuid primary key default gen_random_uuid(),
      prospect_id uuid references public.prospects(id) on delete cascade,
      inbound_reply_id uuid references public.aria_inbound_replies(id) on delete set null,
      action_type text not null
        check (action_type in (
          'follow_up_48hr',
          'nurture_weekly',
          'call_reminder_24hr',
          'ooo_return_followup',
          'snooze_90d'
        )),
      payload jsonb not null default '{}'::jsonb,
      due_at timestamptz not null,
      status text not null default 'pending'
        check (status in ('pending', 'in_flight', 'done', 'cancelled', 'failed')),
      attempts integer not null default 0,
      last_error text,
      last_attempt_at timestamptz,
      completed_at timestamptz,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now()
    );
  end if;
end
$rebuild_scheduled$;

create index if not exists idx_aria_scheduled_actions_due
  on public.aria_scheduled_actions (status, due_at)
  where status = 'pending';

create index if not exists idx_aria_scheduled_actions_prospect
  on public.aria_scheduled_actions (prospect_id, action_type);


create or replace function public.aria_scheduled_actions_touch()
  returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists tg_aria_scheduled_actions_touch on public.aria_scheduled_actions;
create trigger tg_aria_scheduled_actions_touch
  before update on public.aria_scheduled_actions
  for each row execute function public.aria_scheduled_actions_touch();


alter table public.aria_scheduled_actions enable row level security;

drop policy if exists "aria_scheduled_actions_rw" on public.aria_scheduled_actions;
do $policy$
begin
  if exists (
    select 1 from pg_proc p join pg_namespace n on p.pronamespace = n.oid
    where n.nspname = 'public' and p.proname = 'crm_is_privileged'
  ) then
    execute $sql$
      create policy "aria_scheduled_actions_rw"
        on public.aria_scheduled_actions for all
        using (public.crm_is_privileged())
        with check (public.crm_is_privileged())
    $sql$;
  else
    -- Fallback: service-role only (no anon access). The PostgREST service-role
    -- key bypasses RLS entirely, so this is safe; we just don't grant anon.
    execute $sql$
      create policy "aria_scheduled_actions_rw"
        on public.aria_scheduled_actions for all
        using (false)
        with check (false)
    $sql$;
  end if;
end
$policy$;


-- ---------------------------------------------------------------------------
-- 4) crm_settings seeds.
-- ---------------------------------------------------------------------------
insert into public.crm_settings (key, value) values
  ('autonomous_reply_enabled', 'true'),
  ('aria_auto_reply_enabled', 'true'),
  ('aria_nurture_enabled', 'true'),
  ('aria_human_checkpoint_usd_threshold', '5000'),
  ('kevin_sms_number', '')
on conflict (key) do nothing;
