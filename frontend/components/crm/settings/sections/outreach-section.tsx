"use client";

import { Field, SettingsCard, TextInput, Toggle } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;
type OnChange = (key: string, value: string) => void;

export function OutreachSection({ value, onChange }: { value: ValueGetter; onChange: OnChange }) {
  return (
    <>
      <SettingsCard
        title="Pipeline switches"
        description="Master kill switches. Toggling OFF stops the corresponding cron job mid-day without a deploy."
      >
        <Toggle
          label="Rolling dispatcher"
          description="9am–4pm MST rolling send — 600/day across campaigns."
          value={value("pipeline_dispatch_enabled")}
          onChange={(v) => onChange("pipeline_dispatch_enabled", v)}
        />
        <Toggle
          label="Nightly pipeline"
          description="Google Places discovery + enrichment run overnight."
          value={value("pipeline_nightly_enabled")}
          onChange={(v) => onChange("pipeline_nightly_enabled", v)}
        />
      </SettingsCard>

      <SettingsCard
        title="Daily caps per vertical"
        description="Hard limits. The rolling dispatcher enforces these before handing off to Smartlead."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Dental / day">
            <TextInput type="number" min={0} value={value("daily_cap_dental")} onChange={(v) => onChange("daily_cap_dental", v)} />
          </Field>
          <Field label="Legal / day">
            <TextInput type="number" min={0} value={value("daily_cap_legal")} onChange={(v) => onChange("daily_cap_legal", v)} />
          </Field>
          <Field label="Accounting / day">
            <TextInput type="number" min={0} value={value("daily_cap_accounting")} onChange={(v) => onChange("daily_cap_accounting", v)} />
          </Field>
        </div>
        <Field label="Per-inbox daily cap" hint="Max sends per Smartlead inbox per day (reputation cap).">
          <TextInput type="number" min={0} value={value("per_inbox_daily_cap")} onChange={(v) => onChange("per_inbox_daily_cap", v)} />
        </Field>
      </SettingsCard>

      <SettingsCard title="Send window" description="Dispatcher only fires inside this window (MST).">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Start hour (0-23)">
            <TextInput type="number" min={0} max={23} value={value("dispatch_window_start_hour")} onChange={(v) => onChange("dispatch_window_start_hour", v)} />
          </Field>
          <Field label="End hour (0-23)">
            <TextInput type="number" min={0} max={23} value={value("dispatch_window_end_hour")} onChange={(v) => onChange("dispatch_window_end_hour", v)} />
          </Field>
        </div>
      </SettingsCard>
    </>
  );
}
