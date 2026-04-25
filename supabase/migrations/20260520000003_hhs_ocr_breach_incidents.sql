-- HHS OCR public breach database mirror.
--
-- Source: https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf
-- Contains every HIPAA breach affecting 500+ individuals reported to the
-- HHS Office for Civil Rights.
--
-- Used by Charlotte cold-outreach to inject a real, citable breach incident
-- into each cold email's body ("per the HHS OCR public breach database, ..."),
-- selected by the prospect's industry + state + finding type.
--
-- Loader: backend/services/hhs_breach_loader.py (run weekly via cron).
-- Lookup: backend/services/hhs_breach_lookup.py.
-- Idempotent.

CREATE TABLE IF NOT EXISTS public.hhs_ocr_breach_incidents (
  -- Stable hash identity so repeated weekly scrapes don't duplicate rows.
  id text primary key,
  covered_entity_name text not null,
  state text,
  entity_type text,
  -- 'Healthcare Provider', 'Health Plan', 'Business Associate', 'Healthcare Clearing House'
  individuals_affected integer,
  breach_submission_date date,
  -- 'Hacking/IT Incident', 'Unauthorized Access/Disclosure', 'Theft', 'Loss', 'Improper Disposal'
  breach_type text,
  -- 'Network Server', 'Email', 'Electronic Medical Record', 'Paper/Films', etc.
  breach_location text,
  business_associate_present boolean,
  web_description text,
  scraped_at timestamptz not null default now()
);

CREATE INDEX IF NOT EXISTS idx_hhs_breach_state_entity
  ON public.hhs_ocr_breach_incidents (entity_type, state, breach_submission_date desc);

CREATE INDEX IF NOT EXISTS idx_hhs_breach_location
  ON public.hhs_ocr_breach_incidents (breach_location, breach_submission_date desc);

CREATE INDEX IF NOT EXISTS idx_hhs_breach_date
  ON public.hhs_ocr_breach_incidents (breach_submission_date desc);


-- RLS: read-only to all authenticated app users; writes via service role only.
ALTER TABLE public.hhs_ocr_breach_incidents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "hhs_ocr_breach_incidents_read" ON public.hhs_ocr_breach_incidents;
CREATE POLICY "hhs_ocr_breach_incidents_read"
  ON public.hhs_ocr_breach_incidents FOR SELECT
  USING (true);
