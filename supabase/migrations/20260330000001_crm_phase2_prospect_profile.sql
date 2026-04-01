-- Phase 2 — Prospect profile: notes, files, scans, email events stub, onboarding, contact fields

alter table public.profiles
  add column if not exists onboarding_checklist jsonb default '{"whatsapp":false,"video":false,"first_prospect":false,"profile":false}'::jsonb;

alter table public.prospects
  add column if not exists contact_name text,
  add column if not exists contact_email text,
  add column if not exists phone text;

-- ---------------------------------------------------------------------------
-- Prospect notes (timeline + notes tab)
-- ---------------------------------------------------------------------------
create table if not exists public.prospect_notes (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  author_id uuid not null references public.profiles (id),
  body text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_prospect_notes_prospect on public.prospect_notes (prospect_id);
create index if not exists idx_prospect_notes_author on public.prospect_notes (author_id);

-- ---------------------------------------------------------------------------
-- Prospect files (URLs / attachments metadata)
-- ---------------------------------------------------------------------------
create table if not exists public.prospect_files (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  title text not null,
  file_url text not null,
  kind text default 'link' check (kind in ('link', 'pdf', 'loom', 'other')),
  created_by uuid references public.profiles (id),
  created_at timestamptz not null default now()
);

create index if not exists idx_prospect_files_prospect on public.prospect_files (prospect_id);

-- ---------------------------------------------------------------------------
-- CRM prospect scans (HAWK scanner results per prospect)
-- ---------------------------------------------------------------------------
create table if not exists public.crm_prospect_scans (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  hawk_score int,
  grade text,
  findings jsonb default '{}'::jsonb,
  status text not null default 'complete' check (status in ('pending', 'complete', 'failed')),
  triggered_by uuid references public.profiles (id),
  created_at timestamptz not null default now()
);

create index if not exists idx_crm_prospect_scans_prospect on public.crm_prospect_scans (prospect_id);

-- ---------------------------------------------------------------------------
-- Email events (Charlotte / Smartlead — populated in Phase 3)
-- ---------------------------------------------------------------------------
create table if not exists public.prospect_email_events (
  id uuid primary key default gen_random_uuid(),
  prospect_id uuid not null references public.prospects (id) on delete cascade,
  subject text,
  sent_at timestamptz,
  opened_at timestamptz,
  clicked_at timestamptz,
  replied_at timestamptz,
  sequence_step int,
  created_at timestamptz not null default now()
);

create index if not exists idx_prospect_email_events_prospect on public.prospect_email_events (prospect_id);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.prospect_notes enable row level security;
alter table public.prospect_files enable row level security;
alter table public.crm_prospect_scans enable row level security;
alter table public.prospect_email_events enable row level security;

drop policy if exists "prospect_notes_select" on public.prospect_notes;
create policy "prospect_notes_select"
  on public.prospect_notes for select
  using (
    public.crm_is_privileged()
    or (
      author_id = auth.uid()
      and exists (
        select 1 from public.prospects p
        where p.id = prospect_notes.prospect_id
          and (
            p.assigned_rep_id = auth.uid()
            or public.crm_is_team_member(p.assigned_rep_id)
          )
      )
    )
  );

drop policy if exists "prospect_notes_insert" on public.prospect_notes;
create policy "prospect_notes_insert"
  on public.prospect_notes for insert
  with check (
    author_id = auth.uid()
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

drop policy if exists "prospect_notes_update" on public.prospect_notes;
create policy "prospect_notes_update"
  on public.prospect_notes for update
  using (author_id = auth.uid())
  with check (author_id = auth.uid());

drop policy if exists "prospect_files_select" on public.prospect_files;
drop policy if exists "prospect_files_insert" on public.prospect_files;
drop policy if exists "prospect_files_delete" on public.prospect_files;
create policy "prospect_files_select"
  on public.prospect_files for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_files.prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

create policy "prospect_files_insert"
  on public.prospect_files for insert
  with check (
    created_by = auth.uid()
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

create policy "prospect_files_delete"
  on public.prospect_files for delete
  using (
    created_by = auth.uid()
    or public.crm_is_privileged()
  );

drop policy if exists "crm_scans_select" on public.crm_prospect_scans;
drop policy if exists "crm_scans_insert" on public.crm_prospect_scans;
create policy "crm_scans_select"
  on public.crm_prospect_scans for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = crm_prospect_scans.prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

create policy "crm_scans_insert"
  on public.crm_prospect_scans for insert
  with check (
    triggered_by = auth.uid()
    and exists (
      select 1 from public.prospects p
      where p.id = prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

drop policy if exists "email_events_select" on public.prospect_email_events;
create policy "email_events_select"
  on public.prospect_email_events for select
  using (
    exists (
      select 1 from public.prospects p
      where p.id = prospect_email_events.prospect_id
        and (
          public.crm_is_privileged()
          or p.assigned_rep_id = auth.uid()
          or public.crm_is_team_member(p.assigned_rep_id)
        )
    )
  );

-- Service role / Phase 3 will insert email events via backend

-- CEO profile anchor
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
