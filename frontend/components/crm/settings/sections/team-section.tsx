"use client";

import { Field, SettingsCard, TextInput, Toggle } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;
type OnChange = (key: string, value: string) => void;

export function TeamSection({ value, onChange }: { value: ValueGetter; onChange: OnChange }) {
  return (
    <>
      <SettingsCard title="Compensation" description="Applied to all reps unless overridden per-user.">
        <Field label="Commission rate" hint="Fraction of client MRR earned on close. 0.3 = 30%.">
          <TextInput type="number" step={0.01} min={0} max={1} value={value("commission_rate")} onChange={(v) => onChange("commission_rate", v)} />
        </Field>
        <Field label="Monthly close target" hint="Default closes/rep/month for rep scorecards.">
          <TextInput type="number" min={0} value={value("monthly_close_target")} onChange={(v) => onChange("monthly_close_target", v)} />
        </Field>
        <Field label="Guarantee days" hint="Risk-reversal window offered to closed-won clients.">
          <TextInput type="number" min={0} value={value("guarantee_days")} onChange={(v) => onChange("guarantee_days", v)} />
        </Field>
      </SettingsCard>

      <SettingsCard title="Pipeline aging" description="When prospects sit too long, the UI flags the owning rep.">
        <Field label="Warning after (days)">
          <TextInput type="number" min={1} value={value("aging_days_warning")} onChange={(v) => onChange("aging_days_warning", v)} />
        </Field>
        <Field label="Critical after (days)">
          <TextInput type="number" min={1} value={value("aging_days_critical")} onChange={(v) => onChange("aging_days_critical", v)} />
        </Field>
      </SettingsCard>

      <SettingsCard title="Assignment" description="Controls how inbound prospects get a rep.">
        <Toggle
          label="Auto-assign new prospects"
          description="Round-robin every new lead to the next available rep."
          value={value("auto_assign_enabled")}
          onChange={(v) => onChange("auto_assign_enabled", v)}
        />
      </SettingsCard>
    </>
  );
}
