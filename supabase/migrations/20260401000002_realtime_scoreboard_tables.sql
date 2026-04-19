-- Realtime updates for live scoreboard (prospects already published in Phase 1)

alter table public.clients replica identity full;
alter table public.crm_commissions replica identity full;

do $realtime$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'clients'
  ) then
    alter publication supabase_realtime add table public.clients;
  end if;
end;
$realtime$;

do $realtime$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'crm_commissions'
  ) then
    alter publication supabase_realtime add table public.crm_commissions;
  end if;
end;
$realtime$;
