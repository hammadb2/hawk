-- Phase 4 — Commissions: one row per client (30% of MRR at close), auto-created on client insert

create table if not exists public.crm_commissions (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete cascade,
  rep_id uuid not null references public.profiles (id),
  basis_mrr_cents int not null check (basis_mrr_cents >= 0),
  amount_cents int not null check (amount_cents >= 0),
  rate numeric(6,5) not null default 0.30,
  status text not null default 'pending' check (status in ('pending', 'approved', 'paid')),
  created_at timestamptz not null default now(),
  constraint crm_commissions_one_per_client unique (client_id)
);

create index if not exists idx_crm_commissions_rep on public.crm_commissions (rep_id);
create index if not exists idx_crm_commissions_created on public.crm_commissions (created_at desc);

alter table public.crm_commissions enable row level security;

drop policy if exists "crm_commissions_select" on public.crm_commissions;
create policy "crm_commissions_select"
  on public.crm_commissions for select
  using (
    public.crm_is_privileged()
    or rep_id = auth.uid()
    or public.crm_is_team_member(rep_id)
  );

drop policy if exists "crm_commissions_update" on public.crm_commissions;
create policy "crm_commissions_update"
  on public.crm_commissions for update
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

drop policy if exists "crm_commissions_delete" on public.crm_commissions;
create policy "crm_commissions_delete"
  on public.crm_commissions for delete
  using (public.crm_is_privileged());

-- Matches Close Won modal: 30% of first-month MRR
create or replace function public.crm_commission_from_client()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  amt int;
begin
  if new.closing_rep_id is null then
    return new;
  end if;
  amt := (new.mrr_cents * 30) / 100;
  insert into public.crm_commissions (client_id, rep_id, basis_mrr_cents, amount_cents, rate, status)
  values (new.id, new.closing_rep_id, new.mrr_cents, amt, 0.30, 'pending')
  on conflict (client_id) do nothing;
  return new;
end;
$$;

drop trigger if exists trg_clients_create_commission on public.clients;
create trigger trg_clients_create_commission
  after insert on public.clients
  for each row execute function public.crm_commission_from_client();
