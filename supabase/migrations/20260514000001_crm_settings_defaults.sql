-- crm_settings — seed defaults for the rebuilt settings page + remove legacy Charlotte keys.
--
-- Idempotent: re-running this only fills in missing keys, never overwrites
-- values that already exist.

-- Pipeline — dispatch
INSERT INTO public.crm_settings (key, value) VALUES
  ('pipeline_dispatch_enabled', 'true'),
  ('pipeline_nightly_enabled', 'true'),
  ('daily_cap_dental', '200'),
  ('daily_cap_legal', '200'),
  ('daily_cap_accounting', '200'),
  ('daily_send_limit', '600'),
  ('per_inbox_daily_cap', '50'),
  ('dispatch_window_start_hour', '9'),
  ('dispatch_window_end_hour', '16')
ON CONFLICT (key) DO NOTHING;

-- Pipeline — scanner
INSERT INTO public.crm_settings (key, value) VALUES
  ('score_soft_drop_threshold', '85'),
  ('sla_new_stage_minutes', '10'),
  ('sla_scan_concurrency', '3')
ON CONFLICT (key) DO NOTHING;

-- Pipeline — discovery
INSERT INTO public.crm_settings (key, value) VALUES
  (
    'google_places_cities',
    '["Toronto","Vancouver","Calgary","Edmonton","Ottawa","Montreal","Winnipeg","Halifax","Quebec City","Saskatoon","Regina","Victoria","Kelowna","London","Hamilton","Waterloo","Mississauga","Brampton"]'
  ),
  ('google_places_max_per_search', '10'),
  ('discovery_verticals_enabled', '["dental","legal","accounting"]'),
  ('apify_enable_leadsfinder', 'true'),
  ('apify_enable_linkedin', 'true'),
  ('apify_enable_website_crawler', 'false')
ON CONFLICT (key) DO NOTHING;

-- Smartlead campaigns (defaults blank — UI prompts to fill in)
INSERT INTO public.crm_settings (key, value) VALUES
  ('smartlead_campaign_id_dental', ''),
  ('smartlead_campaign_id_legal', ''),
  ('smartlead_campaign_id_accounting', '')
ON CONFLICT (key) DO NOTHING;

-- Team & commissions
INSERT INTO public.crm_settings (key, value) VALUES
  ('commission_rate', '0.3'),
  ('monthly_close_target', '10'),
  ('aging_days_warning', '3'),
  ('aging_days_critical', '7'),
  ('guarantee_days', '90'),
  ('auto_assign_enabled', 'true')
ON CONFLICT (key) DO NOTHING;

-- Notifications
INSERT INTO public.crm_settings (key, value) VALUES
  ('ceo_phone', ''),
  ('slack_webhook_url', ''),
  ('notify_on_scan_fail', 'true'),
  ('notify_on_dispatch_fail', 'true'),
  ('notify_on_pipeline_fail', 'true')
ON CONFLICT (key) DO NOTHING;

-- Branding / general
INSERT INTO public.crm_settings (key, value) VALUES
  ('company_name', 'HAWK Security'),
  ('support_email', 'support@securedbyhawk.com'),
  ('timezone', 'America/Edmonton')
ON CONFLICT (key) DO NOTHING;

-- Remove Charlotte legacy keys — no longer referenced anywhere.
DELETE FROM public.crm_settings
WHERE key IN (
  'charlotte_enabled',
  'charlotte_industry_day_index'
);
