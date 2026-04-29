"use client";

import { Field, SettingsCard, TextInput } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;
type OnChange = (key: string, value: string) => void;

export function GeneralSection({ value, onChange }: { value: ValueGetter; onChange: OnChange }) {
  return (
    <>
      <SettingsCard title="Branding" description="Shown across the app and in outgoing emails.">
        <Field label="Company name">
          <TextInput value={value("company_name")} onChange={(v) => onChange("company_name", v)} placeholder="HAWK Security" />
        </Field>
        <Field label="Support email" hint="Appears in client portal + transactional emails.">
          <TextInput type="email" value={value("support_email")} onChange={(v) => onChange("support_email", v)} placeholder="support@securedbyhawk.com" />
        </Field>
      </SettingsCard>

      <SettingsCard title="Defaults" description="Used wherever the app needs a location or time.">
        <Field label="Timezone" hint="IANA tz used by every scheduler (e.g. America/New_York).">
          <TextInput value={value("timezone")} onChange={(v) => onChange("timezone", v)} placeholder="America/New_York" />
        </Field>
      </SettingsCard>
    </>
  );
}
