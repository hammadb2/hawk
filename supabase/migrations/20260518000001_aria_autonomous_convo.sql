-- ARIA autonomous conversation loop — PR #36.
--
-- Adds:
--   * aria_scheduled_actions   — time-fuse queue for follow-up emails, nurture
--                                 drips, 24-hour call reminders, OOO return
--                                 follow-ups, and 90-day snooze re-engagements.
--   * aria_inbound_replies extensions (auto_sent_at, auto_sent_mailbox_id,
--                                 auto_sent_message_id, checkpoint_reason) so
--                                 we can tell an auto-handled reply from one
--                                 that required the VA queue.
--   * prospects.last_auto_reply_at + prospects.nurture_stopped_at for nurture
--                                 sequence gating.
--   * crm_settings seeds for Kevin's SMS number, the $5k deal threshold, and
--                                 the auto-reply kill switch.
--
-- Idempotent.

create table if not exists public.aria_scheduled_actions (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid references public.prospects(id) on delete cascade,
  inbound_reply_id uuid references public.aria_inbound_replies(id) on delete set null,
  action_type text not null
    check (action_type in (
      'follow_up_48hr',       -- positive reply didn't convert to a booking inside 48h
      'nurture_weekly',       -- part of the 30-day nurture drip
      'call_reminder_24hr',   -- Cal.com booking reminder the day before
      'ooo_return_followup',  -- re-send the pitch after an OOO return date
      'snooze_90d'            -- prospect asked us to circle back in 90 days
    )),
  payload jsonb not null default '{}'::jsonb,  -- action-specific hints (subject template key, nurture week #, alt slot, …)
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
create policy "aria_scheduled_actions_rw"
  on public.aria_scheduled_actions for all
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());


-- aria_inbound_replies — track which replies were handled fully autonomously
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


-- prospects — nurture sequence bookkeeping
alter table public.prospects
  add column if not exists last_auto_reply_at timestamptz,
  add column if not exists nurture_started_at timestamptz,
  add column if not exists nurture_stopped_at timestamptz,
  add column if not exists nurture_stopped_reason text;


-- Seed defaults (safe to rerun).
insert into public.crm_settings (key, value) values
  ('autonomous_reply_enabled', 'true'),
  ('aria_auto_reply_enabled', 'true'),
  ('aria_nurture_enabled', 'true'),
  ('aria_human_checkpoint_usd_threshold', '5000'),
  ('kevin_sms_number', '')
on conflict (key) do nothing;
