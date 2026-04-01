-- Idempotent fix: profiles SELECT must use (select auth.uid()) = id to avoid RLS recursion.
-- Safe on DBs that already ran older migrations with id = auth.uid().

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
  );

drop policy if exists "profiles_update_self" on public.profiles;
create policy "profiles_update_self"
  on public.profiles for update
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

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
