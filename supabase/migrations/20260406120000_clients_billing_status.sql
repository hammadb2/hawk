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
