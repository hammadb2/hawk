-- Portal end-users: role = client (never sales roles). CRM staff remain ceo|hos|team_lead|sales_rep|closer.

alter table public.profiles drop constraint if exists profiles_role_check;

alter table public.profiles
  add constraint profiles_role_check
  check (role in ('ceo', 'hos', 'team_lead', 'sales_rep', 'closer', 'client'));

-- Invite with raw_user_meta_data.portal_client_id: create portal profile row with role client
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
  portal_cid text;
begin
  portal_cid := nullif(trim(coalesce(new.raw_user_meta_data->>'portal_client_id', '')), '');
  if portal_cid is not null and portal_cid <> '' then
    insert into public.profiles (id, email, full_name, role, status)
    values (
      new.id,
      new.email,
      coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
      'client',
      'active'
    )
    on conflict (id) do update
      set email = excluded.email,
          full_name = coalesce(excluded.full_name, public.profiles.full_name),
          role = 'client',
          status = 'active';
    return new;
  end if;

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
