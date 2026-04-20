-- HAWK native cold-outbound mailboxes — replaces Smartlead.
--
-- Stores per-mailbox SMTP + IMAP credentials so the rolling dispatcher can
-- send directly from warmed Mailforge/Google Workspace/custom inboxes without
-- going through a third-party platform. Passwords are encrypted at rest via
-- Fernet (see backend/services/mailbox_crypto.py); the raw ciphertext is what
-- lives in this table.
--
-- Deliverability design:
-- * Each row is one real inbox tied to one sending domain.
-- * `daily_cap` enforces a per-mailbox send ceiling (default 40); dispatcher
--   rotates through active mailboxes in round-robin order so no single inbox
--   blasts.
-- * `sent_today` + `sent_today_date` reset at local midnight via the
--   mailbox_daily_reset cron job — the DB is the source of truth so nothing
--   can drift.
-- * `status` transitions: active → paused (manual or high bounce) → disabled.
-- * `warmup_status` is informational (active mailboxes are assumed warm by
--   v1; auto-warmup is a v2 feature).
--
-- Idempotent — safe to re-run.

create table if not exists public.crm_mailboxes (
  id uuid primary key default gen_random_uuid(),
  email_address text not null unique,
  display_name text not null default '',
  domain text not null,
  provider text not null default 'smtp'
    check (provider in ('smtp', 'google_workspace', 'outlook365', 'mailforge', 'other')),

  -- SMTP (send)
  smtp_host text not null,
  smtp_port integer not null default 587,
  smtp_username text not null,
  smtp_password_encrypted text not null,
  smtp_use_tls boolean not null default true,
  smtp_use_ssl boolean not null default false,

  -- IMAP (receive — reply detection)
  imap_host text not null,
  imap_port integer not null default 993,
  imap_username text not null,
  imap_password_encrypted text not null,
  imap_use_ssl boolean not null default true,
  imap_last_uid_validity bigint,
  imap_last_seen_uid bigint,
  imap_last_polled_at timestamptz,

  -- Quota + rotation
  daily_cap integer not null default 40 check (daily_cap > 0),
  sent_today integer not null default 0 check (sent_today >= 0),
  sent_today_date date not null default ((timezone('America/Edmonton', now()))::date),
  sent_total bigint not null default 0,
  last_send_at timestamptz,

  -- Vertical routing. NULL = available to any vertical (round-robin pool).
  vertical text
    check (vertical is null or vertical in ('dental', 'legal', 'accounting')),

  -- Health
  status text not null default 'active'
    check (status in ('active', 'paused', 'disabled', 'warming')),
  warmup_status text not null default 'active'
    check (warmup_status in ('cold', 'warming', 'active')),
  bounce_count_7d integer not null default 0,
  bounce_rate_7d numeric(5, 4) not null default 0,
  last_bounce_at timestamptz,
  last_error text,

  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid references public.profiles(id) on delete set null
);

create index if not exists idx_crm_mailboxes_rotation
  on public.crm_mailboxes (status, vertical, sent_today_date, sent_today);

create index if not exists idx_crm_mailboxes_domain
  on public.crm_mailboxes (domain);

-- Auto-maintain updated_at on write.
create or replace function public.crm_mailboxes_touch()
  returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists tg_crm_mailboxes_touch on public.crm_mailboxes;
create trigger tg_crm_mailboxes_touch
  before update on public.crm_mailboxes
  for each row execute function public.crm_mailboxes_touch();

alter table public.crm_mailboxes enable row level security;

-- CEO/HOS read/write; everyone else: no access.
drop policy if exists "crm_mailboxes_select" on public.crm_mailboxes;
create policy "crm_mailboxes_select"
  on public.crm_mailboxes for select
  using (public.crm_is_privileged());

drop policy if exists "crm_mailboxes_insert" on public.crm_mailboxes;
create policy "crm_mailboxes_insert"
  on public.crm_mailboxes for insert
  with check (public.crm_is_privileged());

drop policy if exists "crm_mailboxes_update" on public.crm_mailboxes;
create policy "crm_mailboxes_update"
  on public.crm_mailboxes for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

drop policy if exists "crm_mailboxes_delete" on public.crm_mailboxes;
create policy "crm_mailboxes_delete"
  on public.crm_mailboxes for delete
  using (public.crm_is_privileged());


-- ---------------------------------------------------------------------------
-- prospects: track which mailbox sent the email + the RFC 5322 Message-ID so
-- IMAP reply poller can thread replies back to the originating prospect.
-- ---------------------------------------------------------------------------
alter table public.prospects
  add column if not exists sent_via_mailbox_id uuid references public.crm_mailboxes(id) on delete set null,
  add column if not exists sent_message_id text,
  add column if not exists sent_message_id_domain text;

create index if not exists idx_prospects_sent_message_id
  on public.prospects (sent_message_id)
  where sent_message_id is not null;

create index if not exists idx_prospects_sent_via_mailbox
  on public.prospects (sent_via_mailbox_id)
  where sent_via_mailbox_id is not null;

-- ---------------------------------------------------------------------------
-- Seed new crm_settings keys for the mailbox-native dispatcher.
-- ---------------------------------------------------------------------------
insert into public.crm_settings (key, value) values
  ('mailbox_dispatch_enabled', 'true'),
  ('mailbox_default_daily_cap', '40'),
  ('mailbox_bounce_rate_threshold', '0.05'),
  ('mailbox_reply_tracking_enabled', 'true')
on conflict (key) do nothing;
