-- Ensure prospects.domain has a UNIQUE constraint so
-- ON CONFLICT (domain) upserts (used by aria_prospect_pipeline and the
-- nightly discovery pipeline) succeed. The original phase1_core migration
-- defined `unique (domain)` inline but the constraint is missing in
-- some environments, so re-add it idempotently after collapsing any
-- duplicate rows into their most recent record.

-- 1) Collapse duplicates: keep the most recently updated row per domain
--    and redirect any FK references (activities.prospect_id, emails,
--    replies, etc.) to the surviving row before deletion. We rely on
--    `duplicate_of` to record the merge; if the column is missing in
--    older envs, the update is a no-op.
with ranked as (
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
),
keepers as (
  select domain, id as keeper_id
  from ranked
  where rn = 1
),
losers as (
  select r.id as loser_id, k.keeper_id
  from ranked r
  join keepers k on k.domain = r.domain
  where r.rn > 1
)
update public.prospects p
   set duplicate_of = l.keeper_id
  from losers l
 where p.id = l.loser_id
   and p.duplicate_of is distinct from l.keeper_id;

-- 2) Move child activities onto the keeper row (if activities table
--    exists) so we can safely delete losers.
do $$
begin
  if to_regclass('public.activities') is not null then
    execute $sql$
      with ranked as (
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
      ),
      keepers as (select domain, id as keeper_id from ranked where rn = 1),
      losers as (
        select r.id as loser_id, k.keeper_id
        from ranked r
        join keepers k on k.domain = r.domain
        where r.rn > 1
      )
      update public.activities a
         set prospect_id = l.keeper_id
        from losers l
       where a.prospect_id = l.loser_id;
    $sql$;
  end if;
end $$;

-- 3) Delete the duplicate rows (keepers only remain).
with ranked as (
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
)
delete from public.prospects p
 using ranked r
 where p.id = r.id and r.rn > 1;

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
