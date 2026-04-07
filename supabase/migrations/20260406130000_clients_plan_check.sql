-- Portal / checkout insert plan slugs (shield, starter, hawk_*). Drop strict check if it rejects them.
alter table public.clients drop constraint if exists clients_plan_check;
