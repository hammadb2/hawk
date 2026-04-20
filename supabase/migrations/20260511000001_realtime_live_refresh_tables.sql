-- 20260511000001_realtime_live_refresh_tables.sql
--
-- Expand the `supabase_realtime` publication so the CRM + client portal + main
-- app can react to row-level changes on all pipeline- and scan-related tables
-- without a manual refresh.
--
-- Idempotent: each add-table call is guarded so this migration can be re-run
-- safely in any environment (including ones where some of these tables may
-- not exist yet — e.g. older branches).

do $$
declare
  t text;
  tables text[] := array[
    'aria_lead_inventory',
    'aria_pipeline_runs',
    'aria_messages',
    'aria_conversations',
    'crm_prospect_scans',
    'scans',
    'findings',
    'client_domain_scans',
    'client_portal_profiles',
    'suppressions',
    'crm_settings'
  ];
begin
  if not exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    return;
  end if;

  foreach t in array tables loop
    if exists (
      select 1 from information_schema.tables
      where table_schema = 'public' and table_name = t
    ) and not exists (
      select 1
      from pg_publication_tables
      where pubname = 'supabase_realtime'
        and schemaname = 'public'
        and tablename = t
    ) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;
