-- Phase 1 — Rep invite lifecycle, round-robin, Stripe commission deferral

-- Profiles: assignment + onboarding gate + health score (health used in later phases)
alter table public.profiles
  add column if not exists last_assigned_at timestamptz,
  add column if not exists onboarding_completed_at timestamptz,
  add column if not exists health_score int check (health_score is null or (health_score >= 0 and health_score <= 100));

-- Extend CRM lifecycle status (invited → onboarding → active)
alter table public.profiles drop constraint if exists profiles_status_check;
alter table public.profiles
  add constraint profiles_status_check
  check (status in ('invited', 'onboarding', 'active', 'at_risk', 'inactive'));

-- Clients: defer commission until Stripe webhook when payment not verified at close
alter table public.clients
  add column if not exists commission_deferred boolean not null default false;

-- Existing active reps: treat as onboarded (avoid blocking pipeline after migration)
update public.profiles
set onboarding_completed_at = coalesce(onboarding_completed_at, now())
where status = 'active'
  and role in ('sales_rep', 'team_lead')
  and onboarding_completed_at is null;

-- Commission trigger: skip when deferred (webhook creates row later)
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
  if coalesce(new.commission_deferred, false) then
    return new;
  end if;
  amt := (new.mrr_cents * 30) / 100;
  insert into public.crm_commissions (client_id, rep_id, basis_mrr_cents, amount_cents, rate, status)
  values (new.id, new.closing_rep_id, new.mrr_cents, amt, 0.30, 'pending')
  on conflict (client_id) do nothing;
  return new;
end;
$$;

-- New auth users: honor CEO invite metadata (status + whatsapp prefilled)
create or replace function public.crm_handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  initial_status text;
  wa text;
  tl uuid;
begin
  initial_status := nullif(trim(lower(coalesce(new.raw_user_meta_data->>'crm_initial_status', ''))), '');
  wa := nullif(trim(coalesce(new.raw_user_meta_data->>'whatsapp_number', '')), '');
  begin
    tl := (new.raw_user_meta_data->>'crm_team_lead_id')::uuid;
  exception when others then
    tl := null;
  end;

  insert into public.profiles (id, email, full_name, role, status, whatsapp_number, team_lead_id)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
    coalesce(new.raw_user_meta_data->>'crm_role', 'sales_rep'),
    case
      when initial_status in ('invited', 'onboarding') then initial_status
      else 'active'
    end,
    wa,
    tl
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = coalesce(excluded.full_name, public.profiles.full_name);
  return new;
end;
$$;

-- CEO profile anchor
insert into public.profiles (id, email, full_name, role, status, created_at)
values (
  'f04140d6-5f9c-4d93-94b9-5df24555496b',
  'hammadmkac@gmail.com',
  'Hammad Bhatti',
  'ceo',
  'active',
  now()
)
on conflict (id) do update set
  role = 'ceo',
  status = 'active',
  full_name = 'Hammad Bhatti';
