-- Relax the suppressions.reason CHECK so the SLA auto-scan and post-scan
-- pipeline can record descriptive soft-drop reasons without the row being
-- rejected by the original ('unsubscribe', 'bounce', 'manual') constraint.
-- Previously those inserts silently failed under return=minimal headers,
-- which meant we could re-discover dropped domains on the next nightly run.

alter table public.suppressions
  drop constraint if exists suppressions_reason_check;

-- Guarantee the originating dedup key still works even though the list is
-- now open. Keeping the column NOT NULL prevents ambiguous rows.
alter table public.suppressions
  alter column reason set not null;

-- Make (domain, email) pairs idempotent on retry. Without the partial unique
-- indexes the `resolution=merge-duplicates` header on our soft-drop inserts
-- couldn't find anything to merge against, so repeated SLA sweeps would spam
-- duplicate rows each time a stuck prospect re-entered the soft-drop path.
create unique index if not exists suppressions_domain_uniq
  on public.suppressions (domain)
  where domain is not null and email is null;

create unique index if not exists suppressions_email_uniq
  on public.suppressions (email)
  where email is not null and domain is null;

create unique index if not exists suppressions_domain_email_uniq
  on public.suppressions (domain, email)
  where domain is not null and email is not null;
