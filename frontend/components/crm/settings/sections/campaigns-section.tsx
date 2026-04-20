"use client";

import { Field, SettingsCard, TextInput } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;
type OnChange = (key: string, value: string) => void;

export function CampaignsSection({ value, onChange }: { value: ValueGetter; onChange: OnChange }) {
  return (
    <SettingsCard
      title="Smartlead campaigns"
      description="Numeric campaign IDs from Smartlead. The dispatcher routes each prospect to the campaign matching its vertical."
    >
      <Field label="Dental campaign ID" hint="ARIA routes anything classified as dental here.">
        <TextInput value={value("smartlead_campaign_id_dental")} onChange={(v) => onChange("smartlead_campaign_id_dental", v)} placeholder="e.g. 3113200" />
      </Field>
      <Field label="Legal campaign ID">
        <TextInput value={value("smartlead_campaign_id_legal")} onChange={(v) => onChange("smartlead_campaign_id_legal", v)} placeholder="e.g. 3115926" />
      </Field>
      <Field label="Accounting campaign ID">
        <TextInput value={value("smartlead_campaign_id_accounting")} onChange={(v) => onChange("smartlead_campaign_id_accounting", v)} placeholder="e.g. 3115932" />
      </Field>
    </SettingsCard>
  );
}
