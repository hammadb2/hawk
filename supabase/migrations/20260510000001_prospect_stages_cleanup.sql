-- =============================================================================
-- Stage cleanup: replace `loom_sent` with `sent_email`, drop `proposal_sent`.
--
-- New canonical stage order:
--   new -> scanned -> sent_email -> replied -> call_booked -> closed_won
-- Terminal: lost.
--
-- Existing row migration:
--   loom_sent     -> sent_email   (same pre-reply funnel position; rename)
--   proposal_sent -> call_booked  (drop proposal step; fall back to previous)
--
-- Idempotent: safe to re-run. Does not touch rows already on the new values.
-- =============================================================================

-- 1. Temporarily drop the CHECK constraint so we can UPDATE rows through it.
alter table public.prospects
  drop constraint if exists prospects_stage_check;

-- 2. Reparent any existing rows on the removed/renamed stages.
update public.prospects
set stage = 'sent_email',
    last_activity_at = now()
where stage = 'loom_sent';

update public.prospects
set stage = 'call_booked',
    last_activity_at = now()
where stage = 'proposal_sent';

-- 3. Re-add the CHECK constraint with the new stage list.
alter table public.prospects
  add constraint prospects_stage_check
  check (stage in (
    'new',
    'scanned',
    'sent_email',
    'replied',
    'call_booked',
    'closed_won',
    'lost'
  ));
