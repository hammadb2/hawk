-- ARIA Phase 5 — Inbound reply handling (Smartlead webhook → classify → draft → approve → send)
-- =========================================================================

-- ---------------------------------------------------------------------------
-- 1) aria_inbound_replies — stores classified replies with drafted responses
-- ---------------------------------------------------------------------------
create table if not exists public.aria_inbound_replies (
  id uuid primary key default gen_random_uuid(),

  -- Link to prospect
  prospect_id uuid not null references public.prospects (id) on delete cascade,

  -- Link to email event that triggered this
  email_event_id uuid references public.prospect_email_events (id) on delete set null,

  -- Original reply content
  reply_content text not null default '',
  reply_subject text,
  reply_from_email text,
  reply_from_name text,
  reply_received_at timestamptz not null default now(),

  -- ARIA classification
  classification text not null default 'pending'
    check (classification in (
      'pending',        -- not yet classified
      'interested',     -- prospect wants to learn more / book a call
      'objection',      -- prospect raised a concern (price, timing, existing vendor, etc.)
      'not_interested', -- hard no
      'unsubscribe',    -- wants to be removed from list
      'out_of_office',  -- auto-reply / OOO
      'question',       -- asking a question without clear intent
      'positive_other'  -- positive but doesn't fit other categories
    )),
  classification_confidence float,
  classification_reasoning text,

  -- ARIA drafted response
  draft_subject text,
  draft_body text,
  draft_reasoning text,  -- why ARIA chose this response strategy

  -- Approval workflow
  status text not null default 'pending_classification'
    check (status in (
      'pending_classification',  -- waiting for ARIA to classify
      'pending_review',          -- classified + drafted, waiting for human approval
      'approved',                -- human approved, ready to send
      'sent',                    -- response sent via Smartlead
      'rejected',                -- human rejected the draft
      'auto_handled',            -- auto-handled (e.g., OOO, unsubscribe)
      'skipped'                  -- manually skipped
    )),

  -- Who reviewed and when
  reviewed_by uuid references public.profiles (id),
  reviewed_at timestamptz,
  review_note text,

  -- If sent, track delivery
  sent_at timestamptz,
  smartlead_message_id text,

  -- Metadata
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_aria_ir_prospect on public.aria_inbound_replies (prospect_id);
create index if not exists idx_aria_ir_status on public.aria_inbound_replies (status);
create index if not exists idx_aria_ir_classification on public.aria_inbound_replies (classification);
create index if not exists idx_aria_ir_pending on public.aria_inbound_replies (status)
  where status in ('pending_classification', 'pending_review');

alter table public.aria_inbound_replies enable row level security;

-- CEO, HoS, VA Manager can see all replies
drop policy if exists "aria_ir_select" on public.aria_inbound_replies;
create policy "aria_ir_select"
  on public.aria_inbound_replies for select
  using (public.crm_is_privileged());

-- Service role inserts (from webhook / cron)
drop policy if exists "aria_ir_insert" on public.aria_inbound_replies;
create policy "aria_ir_insert"
  on public.aria_inbound_replies for insert
  with check (public.crm_is_privileged());

-- CEO, HoS can approve/reject
drop policy if exists "aria_ir_update" on public.aria_inbound_replies;
create policy "aria_ir_update"
  on public.aria_inbound_replies for update
  using (public.crm_is_privileged());
