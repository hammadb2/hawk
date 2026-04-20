-- Ensure prospects.domain has a UNIQUE constraint so
-- ON CONFLICT (domain) upserts (used by aria_prospect_pipeline and the
-- nightly discovery pipeline) succeed. The original phase1_core migration
-- defined `unique (domain)` inline but the constraint is missing in
-- some environments, so re-add it idempotently after collapsing any
-- duplicate rows into their most recent record.

-- Build a temp table of (loser_id -> keeper_id) for every duplicate domain.
-- Used repeatedly below to reparent child FK rows before deleting the
-- loser prospects. Scoped to this migration via `on commit drop`.
create temporary table if not exists _prospect_dedup_map (
  loser_id uuid primary key,
  keeper_id uuid not null
) on commit drop;

insert into _prospect_dedup_map (loser_id, keeper_id)
select r.id, k.keeper_id
  from (
    select
      id,
      domain,
      row_number() over (
        partition by domain
        order by coalesce(last_activity_at, created_at) desc nulls last,
                 created_at desc nulls last,
                 id::text desc
      ) as rn
    from public.prospects
    where domain is not null and length(trim(domain)) > 0
  ) r
  join (
    select domain, id as keeper_id
      from (
        select
          id,
          domain,
          row_number() over (
            partition by domain
            order by coalesce(last_activity_at, created_at) desc nulls last,
                     created_at desc nulls last,
                     id::text desc
          ) as rn
        from public.prospects
        where domain is not null and length(trim(domain)) > 0
      ) x
     where rn = 1
  ) k on k.domain = r.domain
 where r.rn > 1
on conflict (loser_id) do nothing;

-- 1) Mark losers with duplicate_of = keeper so the merge is traceable.
update public.prospects p
   set duplicate_of = m.keeper_id
  from _prospect_dedup_map m
 where p.id = m.loser_id
   and p.duplicate_of is distinct from m.keeper_id;

-- 2) Reparent every child-table FK that points at a loser. Each block is
--    wrapped in `to_regclass` so the migration is a no-op in envs that
--    haven't created the table yet (phase1 migrations not applied, etc.).

-- clients.prospect_id — NO ACTION (not cascade). Without this, step 3's
-- DELETE would hit a FK violation and abort the migration.
do $$
begin
  if to_regclass('public.clients') is not null then
    execute $sql$
      update public.clients c
         set prospect_id = m.keeper_id
        from _prospect_dedup_map m
       where c.prospect_id = m.loser_id;
    $sql$;
  end if;
end $$;

-- activities.prospect_id — ON DELETE CASCADE. We reparent first so
-- timeline history survives the merge instead of being cascade-deleted.
do $$
begin
  if to_regclass('public.activities') is not null then
    execute $sql$
      update public.activities a
         set prospect_id = m.keeper_id
        from _prospect_dedup_map m
       where a.prospect_id = m.loser_id;
    $sql$;
  end if;
end $$;

-- prospect_notes.prospect_id — ON DELETE CASCADE.
do $$
begin
  if to_regclass('public.prospect_notes') is not null then
    execute $sql$
      update public.prospect_notes n
         set prospect_id = m.keeper_id
        from _prospect_dedup_map m
       where n.prospect_id = m.loser_id;
    $sql$;
  end if;
end $$;

-- prospect_files.prospect_id — ON DELETE CASCADE.
do $$
begin
  if to_regclass('public.prospect_files') is not null then
    execute $sql$
      update public.prospect_files f
         set prospect_id = m.keeper_id
        from _prospect_dedup_map m
       where f.prospect_id = m.loser_id;
    $sql$;
  end if;
end $$;

-- crm_prospect_scans.prospect_id — ON DELETE CASCADE.
do $$
begin
  if to_regclass('public.crm_prospect_scans') is not null then
    execute $sql$
      update public.crm_prospect_scans s
         set prospect_id = m.keeper_id
        from _prospect_dedup_map m
       where s.prospect_id = m.loser_id;
    $sql$;
  end if;
end $$;

-- prospect_email_events.prospect_id — ON DELETE CASCADE.
do $$
begin
  if to_regclass('public.prospect_email_events') is not null then
    execute $sql$
      update public.prospect_email_events e
         set prospect_id = m.keeper_id
        from _prospect_dedup_map m
       where e.prospect_id = m.loser_id;
    $sql$;
  end if;
end $$;

-- prospects.duplicate_of self-FK — if any prior duplicate_of pointed at a
-- loser, re-aim it at the keeper so the loser can be deleted safely.
update public.prospects p
   set duplicate_of = m.keeper_id
  from _prospect_dedup_map m
 where p.duplicate_of = m.loser_id
   and p.id <> m.keeper_id;

-- 3) Delete the now-orphaned loser rows.
delete from public.prospects p
 using _prospect_dedup_map m
 where p.id = m.loser_id;

-- 4) Add the UNIQUE constraint on domain (idempotent).
do $$
begin
  if not exists (
    select 1
    from pg_constraint c
    join pg_class t on t.oid = c.conrelid
    join pg_namespace n on n.oid = t.relnamespace
    where n.nspname = 'public'
      and t.relname = 'prospects'
      and c.contype = 'u'
      and (
        select array_agg(attname order by attnum)
        from pg_attribute
        where attrelid = t.oid and attnum = any(c.conkey)
      ) = array['domain']::name[]
  ) then
    alter table public.prospects
      add constraint prospects_domain_unique unique (domain);
  end if;
end $$;
