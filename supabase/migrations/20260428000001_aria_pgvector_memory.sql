-- ARIA Phase 4 — Semantic memory via pgvector
-- =========================================================================
-- Enable pgvector extension (Supabase supports this natively)
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- 1) aria_memories — stores embedded CRM events for semantic retrieval
-- ---------------------------------------------------------------------------
create table if not exists public.aria_memories (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,          -- e.g. 'prospect_stage_change', 'client_onboarded', 'scan_completed', 'email_sent', 'deal_closed', 'note_added'
  event_id text,                     -- original record ID for dedup
  source_table text,                 -- which table the event came from
  actor_id uuid references public.profiles (id) on delete set null,
  subject_id text,                   -- prospect_id, client_id, etc.
  subject_type text,                 -- 'prospect', 'client', 'va', 'pipeline_run'
  summary text not null,             -- human-readable one-line summary
  detail text not null default '',   -- longer context for the embedding
  metadata jsonb not null default '{}'::jsonb,
  embedding extensions.vector(1536), -- OpenAI text-embedding-3-small dimension
  created_at timestamptz not null default now()
);

-- Indexes for efficient retrieval
create index if not exists idx_aria_mem_event_type on public.aria_memories (event_type);
create index if not exists idx_aria_mem_subject on public.aria_memories (subject_type, subject_id);
create index if not exists idx_aria_mem_created on public.aria_memories (created_at desc);
create index if not exists idx_aria_mem_event_id on public.aria_memories (event_id) where event_id is not null;

-- HNSW index for fast approximate nearest-neighbor search
create index if not exists idx_aria_mem_embedding on public.aria_memories
  using hnsw (embedding extensions.vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- RLS
alter table public.aria_memories enable row level security;

drop policy if exists "aria_mem_select" on public.aria_memories;
create policy "aria_mem_select"
  on public.aria_memories for select
  using (public.crm_is_privileged());

drop policy if exists "aria_mem_insert" on public.aria_memories;
create policy "aria_mem_insert"
  on public.aria_memories for insert
  with check (public.crm_is_privileged());

drop policy if exists "aria_mem_delete" on public.aria_memories;
create policy "aria_mem_delete"
  on public.aria_memories for delete
  using (public.crm_is_privileged());

-- ---------------------------------------------------------------------------
-- 2) RPC function for semantic search (cosine similarity)
-- ---------------------------------------------------------------------------
create or replace function public.aria_memory_search(
  query_embedding extensions.vector(1536),
  match_count int default 10,
  similarity_threshold float default 0.7,
  filter_event_type text default null,
  filter_subject_type text default null,
  filter_subject_id text default null
)
returns table (
  id uuid,
  event_type text,
  subject_type text,
  subject_id text,
  summary text,
  detail text,
  metadata jsonb,
  similarity float,
  created_at timestamptz
)
language plpgsql
security definer
as $$
begin
  return query
  select
    m.id,
    m.event_type,
    m.subject_type,
    m.subject_id,
    m.summary,
    m.detail,
    m.metadata,
    1 - (m.embedding <=> query_embedding) as similarity,
    m.created_at
  from public.aria_memories m
  where
    m.embedding is not null
    and 1 - (m.embedding <=> query_embedding) >= similarity_threshold
    and (filter_event_type is null or m.event_type = filter_event_type)
    and (filter_subject_type is null or m.subject_type = filter_subject_type)
    and (filter_subject_id is null or m.subject_id = filter_subject_id)
  order by m.embedding <=> query_embedding
  limit match_count;
end;
$$;
