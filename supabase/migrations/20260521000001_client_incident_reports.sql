-- Client-reported incident reports — priority list #34.
--
-- One row per "I think we're breached, help now" click from the portal.
-- Captures the SLA clock (reported_at + sla_response_minutes), notification
-- fan-out status (ceo_sms, client_email, support_ticket), and a free-form
-- user description. Rows are written service-role only; clients read their
-- own via RLS; CEO/HoS read everything.

create table if not exists public.client_incident_reports (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  -- auth.users id of whoever clicked the button; null if we lose the
  -- session while writing the row (shouldn't happen).
  reported_by_user_id uuid,
  description text not null default '',
  status text not null default 'open'
    check (status in ('open', 'triaged', 'contained', 'resolved', 'closed')),
  reported_at timestamptz not null default now(),
  sla_deadline timestamptz not null,
  -- Notification fan-out results. Stored as text so ops can grep the
  -- value ("sent" vs "skipped:openphone_not_configured" vs "error:...").
  ceo_sms_status text not null default 'pending',
  client_email_status text not null default 'pending',
  -- Foreign key to public.crm_support_tickets when we successfully created
  -- the internal ticket mirror. Nullable: we still log the incident even
  -- if the mirror insert fails (e.g. no CEO profile found).
  support_ticket_id uuid references public.crm_support_tickets (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_client_incident_reports_client on public.client_incident_reports (client_id, reported_at desc);
create index if not exists idx_client_incident_reports_status on public.client_incident_reports (status);
create index if not exists idx_client_incident_reports_sla on public.client_incident_reports (sla_deadline);

alter table public.client_incident_reports enable row level security;

-- Clients read their own incident reports. We key off client_portal_profiles
-- rather than reading auth.uid() directly — matches the pattern used in
-- other portal tables in this repo.
drop policy if exists "client_incident_reports_select_own" on public.client_incident_reports;
create policy "client_incident_reports_select_own"
  on public.client_incident_reports for select
  using (
    client_id in (
      select cpp.client_id from public.client_portal_profiles cpp where cpp.user_id = auth.uid()
    )
    or exists (
      select 1 from public.profiles p
      where p.id = auth.uid() and p.role in ('ceo', 'hos')
    )
  );

-- Writes via service role only (the API endpoint).
drop policy if exists "client_incident_reports_no_anon_writes" on public.client_incident_reports;
create policy "client_incident_reports_no_anon_writes"
  on public.client_incident_reports for all
  using (false)
  with check (false);

create or replace function public.client_incident_reports_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_client_incident_reports_updated on public.client_incident_reports;
create trigger trg_client_incident_reports_updated
  before update on public.client_incident_reports
  for each row execute function public.client_incident_reports_set_updated_at();
