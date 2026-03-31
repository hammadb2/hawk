-- Realtime updates for live scoreboard (prospects already published in Phase 1)

alter table public.clients replica identity full;
alter table public.crm_commissions replica identity full;

alter publication supabase_realtime add table public.clients;
alter publication supabase_realtime add table public.crm_commissions;
