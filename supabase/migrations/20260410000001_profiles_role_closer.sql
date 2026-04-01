-- Charlotte round-robin: allow profiles.role = 'closer' (in addition to sales_rep, etc.)

alter table public.profiles drop constraint if exists profiles_role_check;

alter table public.profiles
  add constraint profiles_role_check
  check (role in ('ceo', 'hos', 'team_lead', 'sales_rep', 'closer'));
