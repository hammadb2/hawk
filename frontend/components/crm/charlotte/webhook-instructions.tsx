"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

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
    <div className="space-y-6 text-sm text-slate-700">
      <p className="text-slate-600">
        Send outbound / engagement events into each prospect&apos;s <strong className="text-slate-800">Emails</strong> tab. The API
        stores rows in Supabase (<code className="text-emerald-600/90">prospect_email_events</code>) using the service role.
      </p>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Endpoint</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <code className="break-all rounded bg-slate-50 px-2 py-1 text-xs text-emerald-700">{url || "(set NEXT_PUBLIC_API_URL)"}</code>
          <Button type="button" size="sm" variant="outline" className="border-slate-200" disabled={!base} onClick={() => copy(url, "url")}>
            {copied === "url" ? "Copied" : "Copy URL"}
          </Button>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Headers</h2>
        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-600">
          {`X-CRM-Webhook-Secret: <CRM_EMAIL_WEBHOOK_SECRET>
Content-Type: application/json`}
        </pre>
        <p className="mt-2 text-xs text-slate-600">
          Set <code className="text-slate-600">CRM_EMAIL_WEBHOOK_SECRET</code> on the HAWK API server (same env as{" "}
          <code className="text-slate-600">SUPABASE_SERVICE_ROLE_KEY</code>).
        </p>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Body</h2>
        <p className="mt-2 text-xs text-slate-600">
          Provide <code className="text-slate-600">prospect_id</code> (uuid) <em>or</em> <code className="text-slate-600">domain</code> (we attach
          to the newest prospect with that domain). Optional timestamps: <code className="text-slate-600">sent_at</code>,{" "}
          <code className="text-slate-600">opened_at</code>, <code className="text-slate-600">clicked_at</code>,{" "}
          <code className="text-slate-600">replied_at</code>. Use <code className="text-slate-600">external_id</code> for idempotent retries.
        </p>
        <pre className="mt-3 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-600">{example}</pre>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="mt-2 border-slate-200"
          onClick={() => copy(example, "json")}
        >
          {copied === "json" ? "Copied" : "Copy example JSON"}
        </Button>
      </section>

      <p className="text-xs text-slate-600">
        Health: <code className="text-slate-600">{base ? `${base}/api/crm/webhooks/email-events/health` : "—"}</code> (no secret; reports whether
        webhook env is present on the API).
      </p>
    </div>
  );
}
