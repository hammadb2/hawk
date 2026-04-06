-- VA / VA Manager — role_type on profiles + prospect access for VA manager + RLS updates

-- ---------------------------------------------------------------------------
-- 1) Column: role_type (orthogonal to sales `role`: ceo|hos|team_lead|sales_rep|closer|client)
-- ---------------------------------------------------------------------------
alter table public.profiles
  add column if not exists role_type text;

update public.profiles set role_type = 'closer' where role_type is null;

update public.profiles set role_type = 'ceo' where role = 'ceo';
update public.profiles set role_type = 'client' where role = 'client';

alter table public.profiles alter column role_type set default 'closer';
alter table public.profiles alter column role_type set not null;

alter table public.profiles drop constraint if exists profiles_role_type_check;
alter table public.profiles
  add constraint profiles_role_type_check
  check (role_type in ('ceo', 'closer', 'va_outreach', 'va_manager', 'csm', 'client'));

create index if not exists idx_profiles_role_type on public.profiles (role_type);

comment on column public.profiles.role_type is
  'Functional bucket: VA outreach, VA manager, CSM, closer, CEO, client. Used with `role` (CRM seat).';

-- ---------------------------------------------------------------------------
-- 2) Prospect access — includes VA manager viewing prospects assigned to VA team
-- ---------------------------------------------------------------------------
create or replace function public.crm_can_access_prospect(prospect_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    public.crm_is_privileged()
    or exists (
      select 1 from public.prospects pr
      where pr.id = prospect_id
        and (
          pr.assigned_rep_id = (select auth.uid())
          or public.crm_is_team_member(pr.assigned_rep_id)
        )
    )
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid())
        and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.prospects pr
      inner join public.profiles rep on rep.id = pr.assigned_rep_id
      where pr.id = prospect_id
        and rep.role_type in ('va_outreach', 'va_manager')
    ),
    false
  );
$$;

-- ---------------------------------------------------------------------------
-- 3) profiles — VA manager can list VA team; cannot use ceo/hos financial privileges
-- ---------------------------------------------------------------------------
drop policy if exists "profiles_select_own_or_privileged" on public.profiles;
create policy "profiles_select_own_or_privileged"
  on public.profiles for select
  using (
    (select auth.uid()) = id
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role = 'team_lead' and public.profiles.team_lead_id = me.id
    )
    or (
      exists (
        select 1 from public.profiles me
        where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      )
      and public.profiles.role_type in ('va_outreach', 'va_manager')
    )
  );

drop policy if exists "profiles_update_va_manager_team" on public.profiles;
create policy "profiles_update_va_manager_team"
  on public.profiles for update
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and public.profiles.role_type in ('va_outreach', 'va_manager')
    and public.profiles.role <> 'ceo'
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and public.profiles.role_type in ('va_outreach', 'va_manager')
    and public.profiles.role <> 'ceo'
  );

-- ---------------------------------------------------------------------------
-- 4) prospects
-- ---------------------------------------------------------------------------
drop policy if exists "prospects_select" on public.prospects;
create policy "prospects_select"
  on public.prospects for select
  using (public.crm_can_access_prospect(id));

drop policy if exists "prospects_insert" on public.prospects;
create policy "prospects_insert"
  on public.prospects for insert
  with check (
    public.crm_is_privileged()
    or assigned_rep_id = (select auth.uid())
  );

drop policy if exists "prospects_update" on public.prospects;
create policy "prospects_update"
  on public.prospects for update
  using (public.crm_can_access_prospect(id))
  with check (public.crm_can_access_prospect(id));

drop policy if exists "prospects_delete" on public.prospects;
create policy "prospects_delete"
  on public.prospects for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 5) activities
-- ---------------------------------------------------------------------------
drop policy if exists "activities_select" on public.activities;
create policy "activities_select"
  on public.activities for select
  using (
    public.crm_is_privileged()
    or exists (
      select 1 from public.prospects pr
      where pr.id = activities.prospect_id
        and public.crm_can_access_prospect(pr.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 6) prospect_notes — keep author-only for reps; VA manager reads notes on VA queue
-- ---------------------------------------------------------------------------
drop policy if exists "prospect_notes_select" on public.prospect_notes;
create policy "prospect_notes_select"
  on public.prospect_notes for select
  using (
    public.crm_is_privileged()
    or (
      author_id = (select auth.uid())
      and exists (
        select 1 from public.prospects p
        where p.id = prospect_notes.prospect_id
          and (
            p.assigned_rep_id = (select auth.uid())
            or public.crm_is_team_member(p.assigned_rep_id)
          )
      )
    )
    or (
      exists (
        select 1 from public.profiles me
        where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      )
      and exists (
        select 1 from public.prospects p
        where p.id = prospect_notes.prospect_id
          and exists (
            select 1 from public.profiles rep
            where rep.id = p.assigned_rep_id
              and rep.role_type in ('va_outreach', 'va_manager')
          )
      )
    )
  );

drop policy if exists "prospect_notes_insert" on public.prospect_notes;
create policy "prospect_notes_insert"
  on public.prospect_notes for insert
  with check (
    author_id = (select auth.uid())
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = (select auth.uid())
          or public.crm_is_team_member(p.assigned_rep_id)
          or public.crm_can_access_prospect(p.id)
        )
    )
  );

-- ---------------------------------------------------------------------------
-- 7) prospect_files
-- ---------------------------------------------------------------------------
drop policy if exists "prospect_files_select" on public.prospect_files;
create policy "prospect_files_select"
  on public.prospect_files for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_files.prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

drop policy if exists "prospect_files_insert" on public.prospect_files;
create policy "prospect_files_insert"
  on public.prospect_files for insert
  with check (
    created_by = (select auth.uid())
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 8) crm_prospect_scans
-- ---------------------------------------------------------------------------
drop policy if exists "crm_scans_select" on public.crm_prospect_scans;
create policy "crm_scans_select"
  on public.crm_prospect_scans for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = crm_prospect_scans.prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

drop policy if exists "crm_scans_insert" on public.crm_prospect_scans;
create policy "crm_scans_insert"
  on public.crm_prospect_scans for insert
  with check (
    triggered_by = (select auth.uid())
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 9) prospect_email_events
-- ---------------------------------------------------------------------------
drop policy if exists "email_events_select" on public.prospect_email_events;
create policy "email_events_select"
  on public.prospect_email_events for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_email_events.prospect_id
        and public.crm_can_access_prospect(p.id)
    )
  );

-- ---------------------------------------------------------------------------
-- 10) Auth trigger — set role_type for portal clients + optional crm_role_type metadata
-- ---------------------------------------------------------------------------
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
  meta_rt text;
begin
  portal_cid := nullif(trim(coalesce(new.raw_user_meta_data->>'portal_client_id', '')), '');
  if portal_cid is not null and portal_cid <> '' then
    insert into public.profiles (id, email, full_name, role, status, role_type)
    values (
      new.id,
      new.email,
      coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
      'client',
      'active',
      'client'
    )
    on conflict (id) do update
      set email = excluded.email,
          full_name = coalesce(excluded.full_name, public.profiles.full_name),
          role = 'client',
          role_type = 'client',
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

  meta_rt := nullif(trim(lower(coalesce(new.raw_user_meta_data->>'crm_role_type', ''))), '');
  if meta_rt not in ('ceo', 'closer', 'va_outreach', 'va_manager', 'csm', 'client') then
    meta_rt := null;
  end if;

  insert into public.profiles (id, email, full_name, role, status, whatsapp_number, team_lead_id, role_type)
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
    tl,
    coalesce(meta_rt, 'closer')
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = coalesce(excluded.full_name, public.profiles.full_name);
  return new;
end;
$$;
