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
        <Field label="Max results per search" hint="Google Places cap per city+vertical. Default 40.">
          <TextInput
            type="number"
            min={1}
            max={60}
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
        <Field label="Daily target" hint="Total leads/day across Google Places + Apollo topup. Default 2000.">
          <TextInput
            type="number"
            min={100}
            max={10000}
            value={value("discovery_daily_target")}
            onChange={(v) => onChange("discovery_daily_target", v)}
          />
        </Field>
      </SettingsCard>

      <SettingsCard
        title="Apollo enrichment"
        description="Apify actors 2/3/4 have been retired. Apollo mixed_people/search resolves verified decision-maker contacts per domain."
      >
        <Toggle
          label="Apollo people topup"
          description="If Google Places returns fewer than the daily target, top up with Apollo people search."
          value={value("apollo_people_topup_enabled")}
          onChange={(v) => onChange("apollo_people_topup_enabled", v)}
        />
        <Field
          label="Daily credit cap"
          hint="Soft budget guard — enrichment stops for the day once hit."
        >
          <TextInput
            type="number"
            min={0}
            max={50000}
            value={value("apollo_daily_credit_cap")}
            onChange={(v) => onChange("apollo_daily_credit_cap", v)}
          />
        </Field>
      </SettingsCard>

      <SettingsCard
        title="VA manual-outreach queue"
        description="Prospects past the 600/day automated dispatcher cap are routed to /crm/va for manual outreach."
      >
        <Toggle
          label="VA queue enabled"
          description="If off, overflow prospects stay in 'ready' rather than being routed to va_queue."
          value={value("va_queue_enabled")}
          onChange={(v) => onChange("va_queue_enabled", v)}
        />
        <Field label="Daily target per VA" hint="Used on the /crm/va Team tab to show pacing.">
          <TextInput
            type="number"
            min={1}
            max={500}
            value={value("va_daily_target_per_va")}
            onChange={(v) => onChange("va_daily_target_per_va", v)}
          />
        </Field>
      </SettingsCard>
    </>
  );
}
