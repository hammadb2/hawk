-- Phase 1 RLS acceptance checks (run in Supabase SQL editor as each role via JWT, or review policies)
-- 1) Rep A must not SELECT prospects where assigned_rep_id = Rep B
-- 2) CEO must SELECT all prospects
-- 3) Team Lead must SELECT prospects for reps where team_lead_id = TL id

-- Example: impersonate anon key is not enough — use Supabase "Run as user" in dashboard or REST with user JWT.

select tablename, policyname, cmd, qual, with_check
from pg_policies
where schemaname = 'public' and tablename in ('prospects', 'profiles', 'clients', 'activities')
order by tablename, policyname;
