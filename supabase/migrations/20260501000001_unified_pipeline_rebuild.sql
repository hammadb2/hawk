-- Unified Pipeline Rebuild: aria_lead_inventory, aria_domain_health, aria_inbound_replies, crm_settings keys
-- Replaces Charlotte + ARIA pipeline with nightly build + morning dispatch architecture

-- ============================================================================
-- 1. aria_lead_inventory — central lead storage for nightly pipeline
-- ============================================================================

do $etype$ begin
  create type aria_lead_email_finder as enum ('prospeo', 'apollo', 'pattern');
exception when duplicate_object then null; end $etype$;
do $etype$ begin
  create type aria_lead_zb_result as enum ('valid', 'catch_all', 'invalid', 'removed');
exception when duplicate_object then null; end $etype$;
do $etype$ begin
  create type aria_lead_status as enum (
    'pending',
    'verified',
    'scanned',
    'personalized',
    'ready',
    'dispatched',
    'suppressed'
  );
exception when duplicate_object then null; end $etype$;

CREATE TABLE IF NOT EXISTS aria_lead_inventory (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Discovery fields (Google Places)
  business_name   text NOT NULL,
  domain          text NOT NULL,
  address         text,
  city            text,
  province        text,
  vertical        text NOT NULL,  -- dental, legal, accounting
  google_rating   numeric(2,1),
  review_count    integer,
  google_place_id text,
  -- Contact fields (Prospeo / Apollo)
  contact_name    text,
  contact_email   text,
  contact_title   text,
  email_finder    aria_lead_email_finder,
  -- Verification
  zero_bounce_result aria_lead_zb_result,
  zero_bounce_data jsonb DEFAULT '{}'::jsonb,
  -- Scan results
  hawk_score      integer,
  vulnerability_found text,
  no_finding      boolean DEFAULT false,
  scan_data       jsonb DEFAULT '{}'::jsonb,
  -- Personalized email
  email_subject   text,
  email_body      text,
  -- Scoring
  lead_score      integer DEFAULT 0,
  -- Dispatch
  status          aria_lead_status DEFAULT 'pending',
  smartlead_campaign_id text,
  scheduled_send_at timestamptz,
  dispatched_at   timestamptz,
  -- Suppression tracking
  suppression_reason text,
  -- Metadata
  nightly_run_date date,
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

-- Indexes for common queries
create index if not exists idx_inventory_status on aria_lead_inventory(status);
create index if not exists idx_inventory_vertical_status on aria_lead_inventory(vertical, status);
create index if not exists idx_inventory_domain on aria_lead_inventory(domain);
create index if not exists idx_inventory_email on aria_lead_inventory(contact_email);
create index if not exists idx_inventory_run_date on aria_lead_inventory(nightly_run_date);
create index if not exists idx_inventory_lead_score on aria_lead_inventory(lead_score desc);
create unique index if not exists idx_inventory_domain_email_uniq on aria_lead_inventory(domain, contact_email)
  where contact_email is not null;

-- RLS
alter table aria_lead_inventory enable row level security;
drop policy if exists "service_role_all_inventory" on aria_lead_inventory;
create policy "service_role_all_inventory" on aria_lead_inventory
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- ============================================================================
-- 2. aria_domain_health — inbox health monitoring per sending domain
-- ============================================================================

CREATE TABLE IF NOT EXISTS aria_domain_health (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  domain          text NOT NULL,
  -- Metrics (updated by inbox health cron)
  emails_sent_total     integer DEFAULT 0,
  emails_sent_7d        integer DEFAULT 0,
  bounces_7d            integer DEFAULT 0,
  spam_complaints_7d    integer DEFAULT 0,
  replies_7d            integer DEFAULT 0,
  bounce_rate_7d        numeric(5,4) DEFAULT 0,
  spam_rate_7d          numeric(5,4) DEFAULT 0,
  reply_rate_7d         numeric(5,4) DEFAULT 0,
  -- Blacklist monitoring
  blacklisted           boolean DEFAULT false,
  blacklist_entries     jsonb DEFAULT '[]'::jsonb,
  last_blacklist_check  timestamptz,
  -- Status
  health_status   text DEFAULT 'healthy',  -- healthy, warning, paused
  paused_at       timestamptz,
  pause_reason    text,
  -- Metadata
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

create unique index if not exists idx_domain_health_domain on aria_domain_health(domain);
create index if not exists idx_domain_health_status on aria_domain_health(health_status);

alter table aria_domain_health enable row level security;
drop policy if exists "service_role_all_domain_health" on aria_domain_health;
create policy "service_role_all_domain_health" on aria_domain_health
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- ============================================================================
-- 3. aria_inbound_replies — Smartlead webhook reply tracking
-- ============================================================================

do $etype$ begin
  create type aria_reply_sentiment as enum (
    'positive',
    'objection',
    'not_interested',
    'unsubscribe',
    'out_of_office',
    'question',
    'other'
  );
exception when duplicate_object then null; end $etype$;

do $etype$ begin
  create type aria_reply_status as enum (
    'pending',
    'classified',
    'approved',
    'sent',
    'rejected',
    'auto_handled'
  );
exception when duplicate_object then null; end $etype$;

CREATE TABLE IF NOT EXISTS aria_inbound_replies (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Source
  smartlead_lead_id text,
  smartlead_campaign_id text,
  prospect_email    text NOT NULL,
  prospect_name     text,
  prospect_domain   text,
  -- Reply content
  reply_subject     text,
  reply_body        text NOT NULL,
  reply_received_at timestamptz DEFAULT now(),
  -- ARIA classification
  sentiment         aria_reply_sentiment,
  confidence_score  numeric(3,2),
  classification_reasoning text,
  -- ARIA drafted response
  drafted_response_subject text,
  drafted_response_body text,
  -- Status
  status            aria_reply_status DEFAULT 'pending',
  approved_by       uuid,
  approved_at       timestamptz,
  sent_at           timestamptz,
  -- Link to inventory
  inventory_lead_id uuid REFERENCES aria_lead_inventory(id),
  -- Metadata
  webhook_payload   jsonb DEFAULT '{}'::jsonb,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now()
);

create index if not exists idx_replies_status on aria_inbound_replies(status);
create index if not exists idx_replies_sentiment on aria_inbound_replies(sentiment);
create index if not exists idx_replies_email on aria_inbound_replies(prospect_email);
create index if not exists idx_replies_received on aria_inbound_replies(reply_received_at desc);

alter table aria_inbound_replies enable row level security;
drop policy if exists "service_role_all_replies" on aria_inbound_replies;
create policy "service_role_all_replies" on aria_inbound_replies
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- ============================================================================
-- 4. crm_settings — new configuration keys for unified pipeline
-- ============================================================================

INSERT INTO crm_settings (key, value) VALUES
  ('smartlead_campaign_id_dental', ''),
  ('smartlead_campaign_id_legal', ''),
  ('smartlead_campaign_id_accounting', ''),
  ('daily_send_limit', '3000'),
  ('per_inbox_daily_cap', '50'),
  ('pipeline_nightly_enabled', 'true'),
  ('pipeline_dispatch_enabled', 'true'),
  ('google_places_cities', '["Toronto","Vancouver","Calgary","Edmonton","Ottawa","Montreal","Winnipeg","Halifax","Quebec City","Saskatoon","Regina","Victoria","Kelowna","London","Hamilton","Waterloo","Mississauga","Brampton"]')
ON CONFLICT (key) DO NOTHING;
