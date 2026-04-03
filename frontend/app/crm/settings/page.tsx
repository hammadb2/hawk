import Link from "next/link";
import { CeoHealthSection } from "@/components/crm/settings/ceo-health-section";

export default function CrmSettingsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">CRM settings</h1>
        <p className="mt-1 text-sm text-zinc-500">Reference for operating the HAWK sales CRM (not the customer-facing HAWK app).</p>
      </div>

      <section className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5">
        <h2 className="text-sm font-semibold text-zinc-200">Integrations</h2>
        <ul className="mt-3 list-inside list-disc space-y-2 text-sm text-zinc-400">
          <li>
            <Link href="/crm/charlotte" className="text-emerald-400 hover:underline">
              Charlotte & email webhooks
            </Link>{" "}
            — outbound engagement events into prospect profiles.
          </li>
          <li>
            Backend route <code className="text-zinc-500">POST /api/crm/webhooks/email-events</code> with{" "}
            <code className="text-zinc-500">X-CRM-Webhook-Secret</code> (see <code className="text-zinc-500">backend/.env.example</code>).
          </li>
          <li>
            Prospect scans: <code className="text-zinc-500">NEXT_PUBLIC_API_URL</code> +{" "}
            <code className="text-zinc-500">/api/crm/run-scan</code> (Next.js) calls your FastAPI scanner.
          </li>
        </ul>
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5">
        <h2 className="text-sm font-semibold text-zinc-200">Environment checklist</h2>
        <p className="mt-2 text-xs text-zinc-500">Set these in Vercel / hosting (frontend) and API host (backend). Values are never shown here.</p>
        <ul className="mt-3 space-y-1 font-mono text-xs text-zinc-400">
          <li>NEXT_PUBLIC_SUPABASE_URL</li>
          <li>NEXT_PUBLIC_SUPABASE_ANON_KEY</li>
          <li>NEXT_PUBLIC_SITE_URL (canonical origin — magic links, auth callbacks)</li>
          <li>NEXT_PUBLIC_API_URL</li>
          <li>SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (API)</li>
          <li>SUPABASE_JWT_SECRET (API — invite / verify-payment)</li>
          <li>CRM_PUBLIC_BASE_URL, OPENPHONE_API_KEY, OPENPHONE_FROM_NUMBER, CRM_CEO_PHONE_E164, VA_PHONE_NUMBER (API)</li>
          <li>CRM_EMAIL_WEBHOOK_SECRET (API)</li>
          <li>HAWK_CRM_CRON_SECRET, HAWK_CRON_SECRET, or CRON_SECRET (Railway alias — aging cron)</li>
        </ul>
      </section>

      <CeoHealthSection />

      <section className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5">
        <h2 className="text-sm font-semibold text-zinc-200">Database</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Apply SQL migrations under <code className="text-zinc-500">supabase/migrations/</code> in timestamp order in the Supabase project
          that backs this CRM.
        </p>
      </section>
    </div>
  );
}
