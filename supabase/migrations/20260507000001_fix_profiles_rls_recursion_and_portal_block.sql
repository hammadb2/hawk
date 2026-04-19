-- Fix infinite RLS recursion on public.profiles: policies must not subquery `profiles`
-- in a way that re-enters RLS. Use SECURITY DEFINER helpers (bypass RLS) for all
-- role/self checks. Also replace prospect_notes VA branch; add client_portal INSERT guard.

-- ---------------------------------------------------------------------------
-- Core privilege check (replaces body; same semantics, EXISTS form)
-- ---------------------------------------------------------------------------
create or replace function public.crm_is_privileged()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid()
      and role in ('ceo', 'hos')
  );
$$;

-- Team lead: is the current user a team lead (any rep row with team_lead_id = me is allowed)
create or replace function public.crm_auth_is_team_lead()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid()
      and role = 'team_lead'
  );
$$;

-- Rep row is visible to a team lead when the rep's team_lead_id points to that team lead
create or replace function public.crm_team_lead_can_view_rep(subject_team_lead_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select subject_team_lead_id is not null
    and subject_team_lead_id = auth.uid()
    and public.crm_auth_is_team_lead();
$$;

-- VA manager: current user
create or replace function public.crm_auth_is_va_manager()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid()
      and role_type = 'va_manager'
  );
$$;

-- VA manager can list va_outreach / va_manager profile rows
create or replace function public.crm_va_manager_can_view_va_profile(subject_role_type text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.crm_auth_is_va_manager()
    and coalesce(subject_role_type, '') in ('va_outreach', 'va_manager');
$$;

-- VA manager may update VA team rows (not CEO)
create or replace function public.crm_va_manager_can_update_va_profile(subject_role_type text, subject_sales_role text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.crm_auth_is_va_manager()
    and coalesce(subject_role_type, '') in ('va_outreach', 'va_manager')
    and coalesce(subject_sales_role, '') <> 'ceo';
$$;

-- prospect_notes: avoid inline `exists (select from profiles me where role_type = va_manager)`
create or replace function public.crm_va_manager_can_access_va_prospect(p_prospect_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.crm_auth_is_va_manager()
    and exists (
      select 1 from public.prospects p
      where p.id = p_prospect_id
        and exists (
          select 1 from public.profiles rep
          where rep.id = p.assigned_rep_id
            and rep.role_type in ('va_outreach', 'va_manager')
        )
    );
$$;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
drop policy if exists "profiles_select_own_or_privileged" on public.profiles;
create policy "profiles_select_own_or_privileged"
  on public.profiles for select
  using (
    (select auth.uid()) = id
    or public.crm_is_privileged()
    or public.crm_team_lead_can_view_rep(public.profiles.team_lead_id)
    or public.crm_va_manager_can_view_va_profile(public.profiles.role_type)
  );

drop policy if exists "profiles_update_va_manager_team" on public.profiles;
create policy "profiles_update_va_manager_team"
  on public.profiles for update
  using (public.crm_va_manager_can_update_va_profile(public.profiles.role_type, public.profiles.role))
  with check (public.crm_va_manager_can_update_va_profile(public.profiles.role_type, public.profiles.role));

-- ---------------------------------------------------------------------------
-- prospect_notes
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
    or public.crm_va_manager_can_access_va_prospect(prospect_notes.prospect_id)
  );

-- ---------------------------------------------------------------------------
-- client_portal_profiles: block CRM team from creating a portal row as themselves
-- (defense in depth; API usually uses service role)
-- ---------------------------------------------------------------------------
drop policy if exists "block_crm_team_from_portal" on public.client_portal_profiles;
create policy "block_crm_team_from_portal"
  on public.client_portal_profiles for insert
  with check (
    not exists (
      select 1 from public.profiles p
      where p.id = auth.uid()
        and coalesce(p.role, '') <> 'client'
    )
  );

comment on function public.crm_is_privileged() is
  'CEO/HoS check; SECURITY DEFINER to avoid RLS recursion when used from other policies.';
