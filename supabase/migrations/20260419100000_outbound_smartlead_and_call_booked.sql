-- Outbound pipeline: Smartlead campaign IDs per vertical, pipeline toggles, daily cap; prospects.call_booked_at for Cal.com

INSERT INTO public.crm_settings (key, value) VALUES
  ('smartlead_campaign_id_dental', '3113200'),
  ('smartlead_campaign_id_legal', '3115926'),
  ('smartlead_campaign_id_accounting', '3115932'),
  ('pipeline_nightly_enabled', 'true'),
  ('daily_send_limit', '200')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();

ALTER TABLE public.prospects ADD COLUMN IF NOT EXISTS call_booked_at timestamptz;
