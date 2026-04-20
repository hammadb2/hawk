"use client";

import { Field, SettingsCard, TextInput } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;
type OnChange = (key: string, value: string) => void;

export function ScannerSection({ value, onChange }: { value: ValueGetter; onChange: OnChange }) {
  return (
    <>
      <SettingsCard
        title="SLA auto-scan"
        description="Prospects idle in stage=new are automatically picked up and scanned."
      >
        <Field label="New → scanning SLA (minutes)" hint="How long a prospect can sit as 'new' before auto-scan claims it.">
          <TextInput type="number" min={1} value={value("sla_new_stage_minutes")} onChange={(v) => onChange("sla_new_stage_minutes", v)} />
        </Field>
        <Field label="Concurrent scans" hint="Max scans running at once against hawk-scanner-v2.">
          <TextInput type="number" min={1} max={20} value={value("sla_scan_concurrency")} onChange={(v) => onChange("sla_scan_concurrency", v)} />
        </Field>
      </SettingsCard>

      <SettingsCard
        title="Score gate"
        description="After a scan finishes, prospects with a high (safer) Hawk score are soft-dropped to stage=lost."
      >
        <Field label="Soft-drop threshold" hint="A Hawk score ≥ this value marks the prospect as too secure to sell. Never hard-deletes — writes to suppressions instead.">
          <TextInput type="number" min={0} max={100} value={value("score_soft_drop_threshold")} onChange={(v) => onChange("score_soft_drop_threshold", v)} />
        </Field>
      </SettingsCard>
    </>
  );
}
