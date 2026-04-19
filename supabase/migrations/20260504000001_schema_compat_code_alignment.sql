-- Code/schema alignment — objects referenced by Python that were missing or misnamed.
-- Safe to re-run (idempotent).

-- ---------------------------------------------------------------------------
-- crm_notifications — aria_inbox_health.py POSTs role-scoped alerts here
-- (distinct from public.notifications which is user_id keyed).
-- ---------------------------------------------------------------------------
create table if not exists public.crm_notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_role text not null,
  title text not null,
  body text not null default '',
  category text,
  read boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_crm_notifications_role_unread
  on public.crm_notifications (recipient_role, read, created_at desc);

alter table public.crm_notifications enable row level security;

drop policy if exists "crm_notifications_service_all" on public.crm_notifications;
create policy "crm_notifications_service_all"
  on public.crm_notifications for all
  to public
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "crm_notifications_select_privileged" on public.crm_notifications;
create policy "crm_notifications_select_privileged"
  on public.crm_notifications for select
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- prospect_scans view — aria_memory.py reads /rest/v1/prospect_scans
-- Maps to crm_prospect_scans + prospect domain; severity columns default 0.
-- ---------------------------------------------------------------------------
create or replace view public.prospect_scans as
select
  s.id,
  s.prospect_id,
  coalesce(p.domain, '') as domain,
  coalesce(s.hawk_score, 0) as hawk_score,
  coalesce((s.findings ->> 'critical')::int, 0) as critical,
  coalesce((s.findings ->> 'high')::int, 0) as high,
  coalesce((s.findings ->> 'medium')::int, 0) as medium,
  coalesce((s.findings ->> 'low')::int, 0) as low,
  s.created_at
from public.crm_prospect_scans s
left join public.prospects p on p.id = s.prospect_id;

grant select on public.prospect_scans to authenticated;
grant select on public.prospect_scans to service_role;
