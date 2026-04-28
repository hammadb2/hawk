-- Charlotte: switch dispatch from Smartlead to native HAWK SMTP.
--
-- Adds columns recording which crm_mailbox sent each Charlotte email and the
-- RFC 5322 Message-ID we generated, so the IMAP reply poller can thread
-- replies back to the originating prospect (same path ARIA already uses).
--
-- Idempotent. smartlead_lead_id is preserved (already nullable) for
-- historical rows generated before the switch; new rows leave it null.

alter table public.charlotte_emails
  add column if not exists mailbox_id uuid references public.crm_mailboxes (id),
  add column if not exists message_id text,
  add column if not exists sent_at timestamptz,
  add column if not exists sent_via text,
  add column if not exists send_status text,
  add column if not exists send_error text;

create index if not exists idx_charlotte_emails_mailbox
  on public.charlotte_emails (mailbox_id);
create index if not exists idx_charlotte_emails_message_id
  on public.charlotte_emails (message_id);
create index if not exists idx_charlotte_emails_sent_at
  on public.charlotte_emails (sent_at desc);
