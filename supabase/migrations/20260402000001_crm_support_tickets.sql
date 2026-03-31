-- Phase 8 — Internal support tickets (reps file; CEO/HoS triage via RLS + exec notifications)

create table if not exists public.crm_support_tickets (
  id uuid primary key default gen_random_uuid(),
  subject text not null,
  body text not null default '',
  status text not null default 'open' check (status in ('open', 'in_progress', 'resolved', 'closed')),
  priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),
  requester_id uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_crm_support_tickets_status on public.crm_support_tickets (status);
create index if not exists idx_crm_support_tickets_requester on public.crm_support_tickets (requester_id);
create index if not exists idx_crm_support_tickets_created on public.crm_support_tickets (created_at desc);

alter table public.crm_support_tickets enable row level security;

drop policy if exists "crm_support_tickets_select" on public.crm_support_tickets;
create policy "crm_support_tickets_select"
  on public.crm_support_tickets for select
  using (
    requester_id = auth.uid()
    or public.crm_is_privileged()
  );

drop policy if exists "crm_support_tickets_insert" on public.crm_support_tickets;
create policy "crm_support_tickets_insert"
  on public.crm_support_tickets for insert
  with check (requester_id = auth.uid());

drop policy if exists "crm_support_tickets_update" on public.crm_support_tickets;
create policy "crm_support_tickets_update"
  on public.crm_support_tickets for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

drop policy if exists "crm_support_tickets_delete" on public.crm_support_tickets;
create policy "crm_support_tickets_delete"
  on public.crm_support_tickets for delete
  using (public.crm_is_privileged());

create or replace function public.crm_support_tickets_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_crm_support_tickets_updated on public.crm_support_tickets;
create trigger trg_crm_support_tickets_updated
  before update on public.crm_support_tickets
  for each row execute function public.crm_support_tickets_set_updated_at();

-- Notify CEO + HoS when any ticket is created
create or replace function public.crm_notify_execs_new_ticket()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.notifications (user_id, title, message, type)
  select p.id,
         'New support ticket',
         left(new.subject, 200),
         'info'
  from public.profiles p
  where p.role in ('ceo', 'hos');
  return new;
end;
$$;

drop trigger if exists trg_crm_support_ticket_notify on public.crm_support_tickets;
create trigger trg_crm_support_ticket_notify
  after insert on public.crm_support_tickets
  for each row execute function public.crm_notify_execs_new_ticket();

-- Live bell updates (ignore if already in publication)
alter table public.notifications replica identity full;

do $pub$
begin
  alter publication supabase_realtime add table public.notifications;
exception
  when duplicate_object then
    null;
end;
$pub$;
