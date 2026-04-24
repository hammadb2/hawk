"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { crmFieldSurface, crmSurfaceCard } from "@/lib/crm/crm-surface";

export function WebhookInstructions({ apiBase }: { apiBase: string }) {
  const [copied, setCopied] = useState<string | null>(null);
  const base = apiBase.replace(/\/$/, "");
  const url = `${base}/api/crm/webhooks/email-events`;
  const example = `{
  "contact_email": "alex@acmecorp.ca",
  "domain": "acmecorp.ca",
  "first_name": "Alex",
  "company_name": "Acme Corp",
  "industry": "Manufacturing",
  "hawk_score": 64,
  "subject": "re: acmecorp.ca scan",
  "replied_at": "2026-03-31T18:00:00Z",
  "sequence_step": 1,
  "source": "smartlead",
  "external_id": "sl-reply-abc123"
}`;

  async function copy(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  return (
    <div className="space-y-6 text-sm text-ink-100">
      <p className="text-ink-200">
        Send outbound / engagement events into each prospect&apos;s <strong className="text-white">Emails</strong> tab. The API
        stores rows in Supabase (<code className="text-signal/90">prospect_email_events</code>) using the service role.
      </p>

      <section className={`p-4 ${crmSurfaceCard}`}>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-200">Endpoint</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <code className={`break-all px-2 py-1 text-xs text-signal ${crmFieldSurface}`}>{url || "(set NEXT_PUBLIC_API_URL)"}</code>
          <Button type="button" size="sm" variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" disabled={!base} onClick={() => copy(url, "url")}>
            {copied === "url" ? "Copied" : "Copy URL"}
          </Button>
        </div>
      </section>

      <section className={`p-4 ${crmSurfaceCard}`}>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-200">Headers</h2>
        <pre className={`mt-2 overflow-x-auto p-3 text-xs text-ink-200 ${crmFieldSurface}`}>
          {`X-CRM-Webhook-Secret: <CRM_EMAIL_WEBHOOK_SECRET>
Content-Type: application/json`}
        </pre>
        <p className="mt-2 text-xs text-ink-0">
          Set <code className="text-ink-200">CRM_EMAIL_WEBHOOK_SECRET</code> on the HAWK API server (same env as{" "}
          <code className="text-ink-200">SUPABASE_SERVICE_ROLE_KEY</code>).
        </p>
      </section>

      <section className={`p-4 ${crmSurfaceCard}`}>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-200">Body</h2>
        <p className="mt-2 text-xs text-ink-0">
          Provide <code className="text-ink-200">prospect_id</code> (uuid) <em>or</em> <code className="text-ink-200">domain</code> (we attach
          to the newest prospect with that domain). Optional timestamps: <code className="text-ink-200">sent_at</code>,{" "}
          <code className="text-ink-200">opened_at</code>, <code className="text-ink-200">clicked_at</code>,{" "}
          <code className="text-ink-200">replied_at</code>. Use <code className="text-ink-200">external_id</code> for idempotent retries.
        </p>
        <pre className={`mt-3 overflow-x-auto p-3 text-xs text-ink-200 ${crmFieldSurface}`}>{example}</pre>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="mt-2 border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]"
          onClick={() => copy(example, "json")}
        >
          {copied === "json" ? "Copied" : "Copy example JSON"}
        </Button>
      </section>

      <p className="text-xs text-ink-0">
        Health: <code className="text-ink-200">{base ? `${base}/api/crm/webhooks/email-events/health` : "—"}</code> (no secret; reports whether
        webhook env is present on the API).
      </p>
    </div>
  );
}
