-- Portal: record Breach Response Guarantee acceptance (blocks dashboard until accepted once)

alter table public.client_portal_profiles
  add column if not exists guarantee_terms_accepted_at timestamptz;

comment on column public.client_portal_profiles.guarantee_terms_accepted_at is
  'When the portal user acknowledged the guarantee summary; required before main portal UI.';

drop policy if exists "client_portal_profiles_update_own_acceptance" on public.client_portal_profiles;
create policy "client_portal_profiles_update_own_acceptance"
  on public.client_portal_profiles for update
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
