-- Add contact_title to prospects.
--
-- aria_post_scan_pipeline._fetch_prospect / _patch_prospect, crm_va, crm_cron,
-- aria_lead_inventory and apollo_enrichment all read/write prospects.contact_title
-- (set from Apollo enrichment). The column was on aria_lead_inventory but never
-- mirrored onto prospects, so every post-scan SELECT 400'd.
--
-- Idempotent.
ALTER TABLE public.prospects ADD COLUMN IF NOT EXISTS contact_title text;
