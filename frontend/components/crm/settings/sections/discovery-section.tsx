"use client";

import { ChipListField, Field, SettingsCard, TextInput, Toggle } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;
type OnChange = (key: string, value: string) => void;

export function DiscoverySection({ value, onChange }: { value: ValueGetter; onChange: OnChange }) {
  return (
    <>
      <SettingsCard
        title="Google Places discovery"
        description="Cities ARIA seeds each nightly run from. Updates live — no deploy needed."
      >
        <Field label="Target cities" hint="Comma-separated. Each city is searched per vertical.">
          <ChipListField
            value={value("google_places_cities")}
            onChange={(v) => onChange("google_places_cities", v)}
            placeholder="Toronto, Vancouver, Calgary, …"
          />
        </Field>
        <Field label="Max results per search" hint="Google Places cap per city+vertical. Default 10.">
          <TextInput
            type="number"
            min={1}
            max={20}
            value={value("google_places_max_per_search")}
            onChange={(v) => onChange("google_places_max_per_search", v)}
          />
        </Field>
        <Field label="Verticals enabled" hint='JSON list of {dental, legal, accounting} to actively discover.'>
          <ChipListField
            value={value("discovery_verticals_enabled")}
            onChange={(v) => onChange("discovery_verticals_enabled", v)}
            placeholder="dental, legal, accounting"
          />
        </Field>
      </SettingsCard>

      <SettingsCard
        title="Apify enrichment actors"
        description="Which contact-enrichment actors to run after a scan. Each adds cost — off = skipped."
      >
        <Toggle
          label="Leads Finder"
          description="Actor 2 — pulls decision-maker contact from domain."
          value={value("apify_enable_leadsfinder")}
          onChange={(v) => onChange("apify_enable_leadsfinder", v)}
        />
        <Toggle
          label="LinkedIn company scraper"
          description="Actor 3 — LinkedIn owner/executive lookup."
          value={value("apify_enable_linkedin")}
          onChange={(v) => onChange("apify_enable_linkedin", v)}
        />
        <Toggle
          label="Website crawler"
          description="Actor 4 — generic fallback contact scrape. Slow, expensive."
          value={value("apify_enable_website_crawler")}
          onChange={(v) => onChange("apify_enable_website_crawler", v)}
        />
      </SettingsCard>
    </>
  );
}
