"use client";

import { Field, SettingsCard, TextInput, Toggle } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;
type OnChange = (key: string, value: string) => void;

export function NotificationsSection({ value, onChange }: { value: ValueGetter; onChange: OnChange }) {
  return (
    <>
      <SettingsCard title="CEO contact" description="SMS target for hot-lead pings + pipeline alerts.">
        <Field label="CEO phone" hint="E.164 format (+14035550123).">
          <TextInput type="tel" value={value("ceo_phone")} onChange={(v) => onChange("ceo_phone", v)} placeholder="+14035550123" />
        </Field>
      </SettingsCard>

      <SettingsCard title="Slack" description="Optional — receives pipeline health digests.">
        <Field label="Slack incoming-webhook URL">
          <TextInput type="url" value={value("slack_webhook_url")} onChange={(v) => onChange("slack_webhook_url", v)} placeholder="https://hooks.slack.com/…" />
        </Field>
      </SettingsCard>

      <SettingsCard title="Failure alerts" description="When ON, CEO gets pinged if a background job breaks.">
        <Toggle label="Scan job failures" value={value("notify_on_scan_fail")} onChange={(v) => onChange("notify_on_scan_fail", v)} />
        <Toggle label="Dispatcher failures" value={value("notify_on_dispatch_fail")} onChange={(v) => onChange("notify_on_dispatch_fail", v)} />
        <Toggle label="Nightly pipeline failures" value={value("notify_on_pipeline_fail")} onChange={(v) => onChange("notify_on_pipeline_fail", v)} />
      </SettingsCard>
    </>
  );
}
