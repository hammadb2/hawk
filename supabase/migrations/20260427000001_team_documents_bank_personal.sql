-- Team documents, bank details, personal details + profiles.role constraint update
-- + Supabase Storage bucket for team-documents

-- ---------------------------------------------------------------------------
-- 0) Update profiles.role check to include va_manager and va
-- ---------------------------------------------------------------------------
alter table public.profiles drop constraint if exists profiles_role_check;
alter table public.profiles
  add constraint profiles_role_check
  check (role in ('ceo', 'hos', 'team_lead', 'sales_rep', 'closer', 'client', 'va_manager', 'va'));

-- ---------------------------------------------------------------------------
-- 1) team_personal_details
-- ---------------------------------------------------------------------------
create table if not exists public.team_personal_details (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  phone_number text,
  whatsapp_number text,
  address text,
  country text,
  date_of_birth date,
  emergency_contact_name text,
  emergency_contact_phone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id)
);

create index if not exists idx_team_personal_details_profile on public.team_personal_details (profile_id);

alter table public.team_personal_details enable row level security;

-- Own row
drop policy if exists "team_personal_details_select_own" on public.team_personal_details;
create policy "team_personal_details_select_own"
  on public.team_personal_details for select
  using (profile_id = (select auth.uid()));

drop policy if exists "team_personal_details_update_own" on public.team_personal_details;
create policy "team_personal_details_update_own"
  on public.team_personal_details for update
  using (profile_id = (select auth.uid()))
  with check (profile_id = (select auth.uid()));

drop policy if exists "team_personal_details_insert_own" on public.team_personal_details;
create policy "team_personal_details_insert_own"
  on public.team_personal_details for insert
  with check (profile_id = (select auth.uid()));

-- CEO full access
drop policy if exists "team_personal_details_ceo" on public.team_personal_details;
create policy "team_personal_details_ceo"
  on public.team_personal_details for all
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

-- VA manager access (VAs only)
drop policy if exists "team_personal_details_va_manager" on public.team_personal_details;
create policy "team_personal_details_va_manager"
  on public.team_personal_details for all
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id = team_personal_details.profile_id
        and target.role_type in ('va_outreach')
    )
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id = team_personal_details.profile_id
        and target.role_type in ('va_outreach')
    )
  );

-- ---------------------------------------------------------------------------
-- 2) team_bank_details
-- ---------------------------------------------------------------------------
create table if not exists public.team_bank_details (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  full_name text,
  bank_name text,
  account_number text,
  routing_or_swift text,
  payment_method text default 'bank_transfer'
    check (payment_method in ('wise', 'paypal', 'bank_transfer', 'gcash', 'other')),
  payment_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id)
);

create index if not exists idx_team_bank_details_profile on public.team_bank_details (profile_id);

alter table public.team_bank_details enable row level security;

-- Own row
drop policy if exists "team_bank_details_select_own" on public.team_bank_details;
create policy "team_bank_details_select_own"
  on public.team_bank_details for select
  using (profile_id = (select auth.uid()));

drop policy if exists "team_bank_details_update_own" on public.team_bank_details;
create policy "team_bank_details_update_own"
  on public.team_bank_details for update
  using (profile_id = (select auth.uid()))
  with check (profile_id = (select auth.uid()));

drop policy if exists "team_bank_details_insert_own" on public.team_bank_details;
create policy "team_bank_details_insert_own"
  on public.team_bank_details for insert
  with check (profile_id = (select auth.uid()));

-- CEO full access
drop policy if exists "team_bank_details_ceo" on public.team_bank_details;
create policy "team_bank_details_ceo"
  on public.team_bank_details for all
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

-- VA manager access (VAs only)
drop policy if exists "team_bank_details_va_manager" on public.team_bank_details;
create policy "team_bank_details_va_manager"
  on public.team_bank_details for all
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id = team_bank_details.profile_id
        and target.role_type in ('va_outreach')
    )
  )
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id = team_bank_details.profile_id
        and target.role_type in ('va_outreach')
    )
  );

-- ---------------------------------------------------------------------------
-- 3) team_documents
-- ---------------------------------------------------------------------------
create table if not exists public.team_documents (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  document_type text not null default 'other'
    check (document_type in ('contract', 'id', 'nda', 'other')),
  file_name text not null,
  file_url text not null,
  uploaded_by uuid references public.profiles (id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_team_documents_profile on public.team_documents (profile_id);

alter table public.team_documents enable row level security;

-- Own row
drop policy if exists "team_documents_select_own" on public.team_documents;
create policy "team_documents_select_own"
  on public.team_documents for select
  using (profile_id = (select auth.uid()));

drop policy if exists "team_documents_insert_own" on public.team_documents;
create policy "team_documents_insert_own"
  on public.team_documents for insert
  with check (profile_id = (select auth.uid()));

-- CEO full access (including delete)
drop policy if exists "team_documents_ceo" on public.team_documents;
create policy "team_documents_ceo"
  on public.team_documents for all
  using (public.crm_is_privileged())
  with check (public.crm_is_privileged());

-- VA manager access (VAs only, read + insert only, no delete)
drop policy if exists "team_documents_va_manager_select" on public.team_documents;
create policy "team_documents_va_manager_select"
  on public.team_documents for select
  using (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id = team_documents.profile_id
        and target.role_type in ('va_outreach')
    )
  );

drop policy if exists "team_documents_va_manager_insert" on public.team_documents;
create policy "team_documents_va_manager_insert"
  on public.team_documents for insert
  with check (
    exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id = team_documents.profile_id
        and target.role_type in ('va_outreach')
    )
  );

-- ---------------------------------------------------------------------------
-- 4) Supabase Storage bucket — team-documents (private)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('team-documents', 'team-documents', false)
on conflict (id) do nothing;

-- Storage RLS: owner can upload/read own files
drop policy if exists "team_docs_storage_owner_select" on storage.objects;
create policy "team_docs_storage_owner_select"
  on storage.objects for select
  using (
    bucket_id = 'team-documents'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists "team_docs_storage_owner_insert" on storage.objects;
create policy "team_docs_storage_owner_insert"
  on storage.objects for insert
  with check (
    bucket_id = 'team-documents'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- CEO/HoS can read all files in team-documents bucket
drop policy if exists "team_docs_storage_privileged" on storage.objects;
create policy "team_docs_storage_privileged"
  on storage.objects for select
  using (
    bucket_id = 'team-documents'
    and public.crm_is_privileged()
  );

-- CEO/HoS can delete files in team-documents bucket
drop policy if exists "team_docs_storage_privileged_delete" on storage.objects;
create policy "team_docs_storage_privileged_delete"
  on storage.objects for delete
  using (
    bucket_id = 'team-documents'
    and public.crm_is_privileged()
  );

-- VA manager can read files for VA team members
drop policy if exists "team_docs_storage_va_manager" on storage.objects;
create policy "team_docs_storage_va_manager"
  on storage.objects for select
  using (
    bucket_id = 'team-documents'
    and exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id::text = (storage.foldername(name))[1]
        and target.role_type in ('va_outreach')
    )
  );

-- VA manager can upload files for VA team members
drop policy if exists "team_docs_storage_va_manager_insert" on storage.objects;
create policy "team_docs_storage_va_manager_insert"
  on storage.objects for insert
  with check (
    bucket_id = 'team-documents'
    and exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
    )
    and exists (
      select 1 from public.profiles target
      where target.id::text = (storage.foldername(name))[1]
        and target.role_type in ('va_outreach')
    )
  );
