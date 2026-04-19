-- AI Onboarding Portal + AI Command Center — tables, storage, RLS
-- =========================================================================

-- ---------------------------------------------------------------------------
-- 1) team_personal_details — personal info collected during onboarding
-- ---------------------------------------------------------------------------
create table if not exists public.team_personal_details (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  phone text,
  whatsapp text,
  address text,
  country text,
  date_of_birth date,
  emergency_contact_name text,
  emergency_contact_phone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id)
);

alter table public.team_personal_details enable row level security;

drop policy if exists "tpd_select" on public.team_personal_details;
create policy "tpd_select"
  on public.team_personal_details for select
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      and exists (
        select 1 from public.profiles t
        where t.id = team_personal_details.profile_id and t.role_type in ('va_outreach', 'va_manager')
      )
    )
  );

drop policy if exists "tpd_insert" on public.team_personal_details;
create policy "tpd_insert"
  on public.team_personal_details for insert
  with check (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "tpd_update" on public.team_personal_details;
create policy "tpd_update"
  on public.team_personal_details for update
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

-- ---------------------------------------------------------------------------
-- 2) team_bank_details — bank info collected during onboarding
-- ---------------------------------------------------------------------------
create table if not exists public.team_bank_details (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  full_name text,
  bank_name text,
  account_number text,
  routing_or_swift text,
  payment_method text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id)
);

alter table public.team_bank_details enable row level security;

drop policy if exists "tbd_select" on public.team_bank_details;
create policy "tbd_select"
  on public.team_bank_details for select
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "tbd_insert" on public.team_bank_details;
create policy "tbd_insert"
  on public.team_bank_details for insert
  with check (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "tbd_update" on public.team_bank_details;
create policy "tbd_update"
  on public.team_bank_details for update
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

-- ---------------------------------------------------------------------------
-- 3) onboarding_sessions
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_sessions (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'in_progress'
    check (status in ('in_progress', 'pending_review', 'approved', 'rejected')),
  agreed_terms jsonb default '{}'::jsonb,
  current_step int not null default 1,
  completed_at timestamptz,
  approved_by uuid references public.profiles (id),
  approved_at timestamptz,
  rejected_reason text,
  created_at timestamptz not null default now(),
  unique (profile_id)
);

create index if not exists idx_onboarding_sessions_profile on public.onboarding_sessions (profile_id);
create index if not exists idx_onboarding_sessions_status on public.onboarding_sessions (status);

alter table public.onboarding_sessions enable row level security;

drop policy if exists "obs_select" on public.onboarding_sessions;
create policy "obs_select"
  on public.onboarding_sessions for select
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      and exists (
        select 1 from public.profiles t
        where t.id = onboarding_sessions.profile_id and t.role_type in ('va_outreach', 'va_manager')
      )
    )
  );

drop policy if exists "obs_insert" on public.onboarding_sessions;
create policy "obs_insert"
  on public.onboarding_sessions for insert
  with check (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
  );

drop policy if exists "obs_update" on public.onboarding_sessions;
create policy "obs_update"
  on public.onboarding_sessions for update
  using (
    profile_id = (select auth.uid())
    or public.crm_is_privileged()
    or exists (
      select 1 from public.profiles me
      where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      and exists (
        select 1 from public.profiles t
        where t.id = onboarding_sessions.profile_id and t.role_type in ('va_outreach', 'va_manager')
      )
    )
  );

-- ---------------------------------------------------------------------------
-- 4) onboarding_documents — signed contracts, NDAs, AUPs
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_documents (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.onboarding_sessions (id) on delete cascade,
  document_type text not null
    check (document_type in ('contract', 'nda', 'acceptable_use')),
  file_url text,
  signed_at timestamptz,
  signature_data text,
  ip_address text,
  created_at timestamptz not null default now()
);

create index if not exists idx_onboarding_docs_session on public.onboarding_documents (session_id);

alter table public.onboarding_documents enable row level security;

drop policy if exists "obd_select" on public.onboarding_documents;
create policy "obd_select"
  on public.onboarding_documents for select
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_documents.session_id
        and (
          s.profile_id = (select auth.uid())
          or public.crm_is_privileged()
          or exists (
            select 1 from public.profiles me
            where me.id = (select auth.uid()) and me.role_type = 'va_manager'
            and exists (
              select 1 from public.profiles t
              where t.id = s.profile_id and t.role_type in ('va_outreach', 'va_manager')
            )
          )
        )
    )
  );

drop policy if exists "obd_insert" on public.onboarding_documents;
create policy "obd_insert"
  on public.onboarding_documents for insert
  with check (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

drop policy if exists "obd_update" on public.onboarding_documents;
create policy "obd_update"
  on public.onboarding_documents for update
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_documents.session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

-- ---------------------------------------------------------------------------
-- 5) onboarding_submissions — government ID + bank/personal flags
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_submissions (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.onboarding_sessions (id) on delete cascade,
  government_id_url text,
  bank_details_submitted boolean not null default false,
  personal_details_submitted boolean not null default false,
  created_at timestamptz not null default now(),
  unique (session_id)
);

alter table public.onboarding_submissions enable row level security;

drop policy if exists "obsub_select" on public.onboarding_submissions;
create policy "obsub_select"
  on public.onboarding_submissions for select
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_submissions.session_id
        and (
          s.profile_id = (select auth.uid())
          or public.crm_is_privileged()
          or exists (
            select 1 from public.profiles me
            where me.id = (select auth.uid()) and me.role_type = 'va_manager'
            and exists (
              select 1 from public.profiles t
              where t.id = s.profile_id and t.role_type in ('va_outreach', 'va_manager')
            )
          )
        )
    )
  );

drop policy if exists "obsub_insert" on public.onboarding_submissions;
create policy "obsub_insert"
  on public.onboarding_submissions for insert
  with check (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

drop policy if exists "obsub_update" on public.onboarding_submissions;
create policy "obsub_update"
  on public.onboarding_submissions for update
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_submissions.session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

-- ---------------------------------------------------------------------------
-- 6) onboarding_quiz_results
-- ---------------------------------------------------------------------------
create table if not exists public.onboarding_quiz_results (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.onboarding_sessions (id) on delete cascade,
  module text not null,
  score int not null default 0,
  passed boolean not null default false,
  completed_at timestamptz
);

create index if not exists idx_quiz_results_session on public.onboarding_quiz_results (session_id);

alter table public.onboarding_quiz_results enable row level security;

drop policy if exists "oqr_select" on public.onboarding_quiz_results;
create policy "oqr_select"
  on public.onboarding_quiz_results for select
  using (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = onboarding_quiz_results.session_id
        and (
          s.profile_id = (select auth.uid())
          or public.crm_is_privileged()
          or exists (
            select 1 from public.profiles me
            where me.id = (select auth.uid()) and me.role_type = 'va_manager'
            and exists (
              select 1 from public.profiles t
              where t.id = s.profile_id and t.role_type in ('va_outreach', 'va_manager')
            )
          )
        )
    )
  );

drop policy if exists "oqr_insert" on public.onboarding_quiz_results;
create policy "oqr_insert"
  on public.onboarding_quiz_results for insert
  with check (
    exists (
      select 1 from public.onboarding_sessions s
      where s.id = session_id
        and (s.profile_id = (select auth.uid()) or public.crm_is_privileged())
    )
  );

-- ---------------------------------------------------------------------------
-- 7) ai_action_log — every AI Command Center action
-- (Skip if renamed to aria_action_log in 20260427000001 — avoids duplicate on re-run.)
-- ---------------------------------------------------------------------------
do $t7$ begin
  if to_regclass('public.aria_action_log') is not null or to_regclass('public.ai_action_log') is not null then
    return;
  end if;
  create table public.ai_action_log (
    id uuid primary key default gen_random_uuid(),
    triggered_by uuid not null references public.profiles (id),
    action_type text not null,
    action_payload jsonb default '{}'::jsonb,
    result text,
    created_at timestamptz not null default now()
  );
  create index idx_ai_action_log_by on public.ai_action_log (triggered_by);
  create index idx_ai_action_log_created on public.ai_action_log (created_at desc);
  alter table public.ai_action_log enable row level security;
  create policy "aal_select"
    on public.ai_action_log for select
    using (
      triggered_by = (select auth.uid())
      or public.crm_is_privileged()
    );
  create policy "aal_insert"
    on public.ai_action_log for insert
    with check (
      triggered_by = (select auth.uid())
      or public.crm_is_privileged()
    );
end $t7$;

-- ---------------------------------------------------------------------------
-- 8) scheduled_ai_actions — cron-executed AI actions
-- ---------------------------------------------------------------------------
do $t8$ begin
  if to_regclass('public.aria_scheduled_actions') is not null or to_regclass('public.scheduled_ai_actions') is not null then
    return;
  end if;
  create table public.scheduled_ai_actions (
    id uuid primary key default gen_random_uuid(),
    triggered_by uuid not null references public.profiles (id),
    action_type text not null,
    action_payload jsonb default '{}'::jsonb,
    scheduled_for timestamptz not null,
    executed boolean not null default false,
    executed_at timestamptz,
    created_at timestamptz not null default now()
  );
  create index idx_sched_ai_pending on public.scheduled_ai_actions (executed, scheduled_for);
  alter table public.scheduled_ai_actions enable row level security;
  create policy "saa_select"
    on public.scheduled_ai_actions for select
    using (
      triggered_by = (select auth.uid())
      or public.crm_is_privileged()
    );
  create policy "saa_insert"
    on public.scheduled_ai_actions for insert
    with check (
      triggered_by = (select auth.uid())
      or public.crm_is_privileged()
    );
  create policy "saa_update"
    on public.scheduled_ai_actions for update
    using (public.crm_is_privileged());
end $t8$;

-- ---------------------------------------------------------------------------
-- 9) ai_chat_conversations — persisted AI Command Center conversations
-- ---------------------------------------------------------------------------
do $t9$ begin
  if to_regclass('public.aria_conversations') is not null or to_regclass('public.ai_chat_conversations') is not null then
    return;
  end if;
  create table public.ai_chat_conversations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles (id) on delete cascade,
    title text not null default 'New conversation',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
  );
  create index idx_ai_chat_conv_user on public.ai_chat_conversations (user_id);
  alter table public.ai_chat_conversations enable row level security;
  create policy "acc_select"
    on public.ai_chat_conversations for select
    using (user_id = (select auth.uid()));
  create policy "acc_insert"
    on public.ai_chat_conversations for insert
    with check (user_id = (select auth.uid()));
  create policy "acc_update"
    on public.ai_chat_conversations for update
    using (user_id = (select auth.uid()));
  create policy "acc_delete"
    on public.ai_chat_conversations for delete
    using (user_id = (select auth.uid()));
end $t9$;

-- ---------------------------------------------------------------------------
-- 10) ai_chat_messages — individual messages in conversations
-- ---------------------------------------------------------------------------
do $t10$ begin
  if to_regclass('public.aria_messages') is not null or to_regclass('public.ai_chat_messages') is not null then
    return;
  end if;
  if to_regclass('public.aria_conversations') is not null then
    create table public.ai_chat_messages (
      id uuid primary key default gen_random_uuid(),
      conversation_id uuid not null references public.aria_conversations (id) on delete cascade,
      role text not null check (role in ('user', 'assistant', 'system', 'function')),
      content text not null default '',
      function_name text,
      function_args jsonb,
      function_result text,
      created_at timestamptz not null default now()
    );
  elsif to_regclass('public.ai_chat_conversations') is not null then
    create table public.ai_chat_messages (
      id uuid primary key default gen_random_uuid(),
      conversation_id uuid not null references public.ai_chat_conversations (id) on delete cascade,
      role text not null check (role in ('user', 'assistant', 'system', 'function')),
      content text not null default '',
      function_name text,
      function_args jsonb,
      function_result text,
      created_at timestamptz not null default now()
    );
  else
    return;
  end if;
  create index idx_ai_chat_msgs_conv on public.ai_chat_messages (conversation_id, created_at);
  alter table public.ai_chat_messages enable row level security;
  -- Policies must reference only the parent table that exists (parser validates all names).
  if to_regclass('public.aria_conversations') is not null
     and to_regclass('public.ai_chat_conversations') is null then
    create policy "acm_select"
      on public.ai_chat_messages for select
      using (
        exists (
          select 1 from public.aria_conversations c
          where c.id = ai_chat_messages.conversation_id
            and c.user_id = (select auth.uid())
        )
      );
    create policy "acm_insert"
      on public.ai_chat_messages for insert
      with check (
        exists (
          select 1 from public.aria_conversations c
          where c.id = conversation_id
            and c.user_id = (select auth.uid())
        )
      );
  else
    create policy "acm_select"
      on public.ai_chat_messages for select
      using (
        exists (
          select 1 from public.ai_chat_conversations c
          where c.id = ai_chat_messages.conversation_id
            and c.user_id = (select auth.uid())
        )
      );
    create policy "acm_insert"
      on public.ai_chat_messages for insert
      with check (
        exists (
          select 1 from public.ai_chat_conversations c
          where c.id = conversation_id
            and c.user_id = (select auth.uid())
        )
      );
  end if;
end $t10$;

-- ---------------------------------------------------------------------------
-- 11) Storage bucket for onboarding documents (gov IDs, signed PDFs)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'onboarding-documents',
  'onboarding-documents',
  false,
  52428800,
  array['application/pdf', 'image/png', 'image/jpeg']::text[]
)
on conflict (id) do nothing;

-- Storage policies: user can upload to their own folder; privileged can read all
drop policy if exists "onb_docs_upload" on storage.objects;
create policy "onb_docs_upload"
  on storage.objects for insert
  with check (
    bucket_id = 'onboarding-documents'
    and (
      (storage.foldername(name))[1] = (select auth.uid())::text
      or public.crm_is_privileged()
    )
  );

drop policy if exists "onb_docs_select" on storage.objects;
create policy "onb_docs_select"
  on storage.objects for select
  using (
    bucket_id = 'onboarding-documents'
    and (
      (storage.foldername(name))[1] = (select auth.uid())::text
      or public.crm_is_privileged()
      or exists (
        select 1 from public.profiles me
        where me.id = (select auth.uid()) and me.role_type = 'va_manager'
      )
    )
  );

-- ---------------------------------------------------------------------------
-- 12) Add onboarding_status to profiles for middleware redirect
-- ---------------------------------------------------------------------------
alter table public.profiles
  add column if not exists onboarding_status text
    default null;

comment on column public.profiles.onboarding_status is
  'AI onboarding portal status: in_progress | pending_review | approved | rejected. NULL = no onboarding needed (CEO, legacy).';

-- Update status check to include onboarding-related statuses
alter table public.profiles drop constraint if exists profiles_status_check;
alter table public.profiles
  add constraint profiles_status_check
  check (status in ('active', 'at_risk', 'inactive', 'invited', 'onboarding'));
