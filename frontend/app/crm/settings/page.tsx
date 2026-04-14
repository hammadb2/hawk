"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CeoHealthSection } from "@/components/crm/settings/ceo-health-section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type CrmConfig = {
  id?: string;
  commission_rate: number;
  monthly_close_target: number;
  aging_days_warning: number;
  aging_days_critical: number;
  guarantee_days: number;
  auto_assign_enabled: boolean;
  charlotte_enabled: boolean;
};

const DEFAULTS: CrmConfig = {
  commission_rate: 0.3,
  monthly_close_target: 10,
  aging_days_warning: 3,
  aging_days_critical: 7,
  guarantee_days: 90,
  auto_assign_enabled: true,
  charlotte_enabled: true,
};

export default function CrmSettingsPage() {
  const supabase = useMemo(() => createClient(), []);
  const { profile } = useCrmAuth();
  const [config, setConfig] = useState<CrmConfig>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("crm_settings")
      .select("*")
      .limit(1)
      .maybeSingle();
    if (error) {
      setConfig(DEFAULTS);
    } else if (data) {
      setConfig(data as CrmConfig);
    }
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (profile?.role === "ceo") void load();
    else setLoading(false);
  }, [profile?.role, load]);

  async function save() {
    setSaving(true);
    const payload = {
      commission_rate: config.commission_rate,
      monthly_close_target: config.monthly_close_target,
      aging_days_warning: config.aging_days_warning,
      aging_days_critical: config.aging_days_critical,
      guarantee_days: config.guarantee_days,
      auto_assign_enabled: config.auto_assign_enabled,
      charlotte_enabled: config.charlotte_enabled,
    };
    if (config.id) {
      const { error } = await supabase.from("crm_settings").update(payload).eq("id", config.id);
      if (error) toast.error(error.message);
      else toast.success("Settings saved");
    } else {
      const { error } = await supabase.from("crm_settings").insert(payload);
      if (error) toast.error(error.message);
      else {
        toast.success("Settings saved");
        await load();
      }
    }
    setSaving(false);
  }

  function updateField<K extends keyof CrmConfig>(key: K, value: CrmConfig[K]) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  if (profile?.role !== "ceo") {
    return (
      <div className="mx-auto max-w-2xl space-y-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">CRM settings</h1>
          <p className="mt-1 text-sm text-slate-600">Only the CEO can modify CRM settings.</p>
        </div>
        <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
          <h2 className="text-sm font-semibold text-slate-800">Integrations</h2>
          <ul className="mt-3 list-inside list-disc space-y-2 text-sm text-slate-600">
            <li>
              <Link href="/crm/charlotte" className="text-emerald-600 hover:underline">
                Charlotte & email webhooks
              </Link>{" "}
              — outbound engagement events into prospect profiles.
            </li>
          </ul>
        </section>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">CRM settings</h1>
        <p className="mt-1 text-sm text-slate-600">Configure CRM behavior. Changes take effect immediately.</p>
      </div>

      {loading ? (
        <div className="py-12 text-center text-slate-600">Loading…</div>
      ) : (
        <>
          <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-800">Commission & targets</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label className="text-xs text-slate-600">Commission rate (%)</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  className="border-slate-200 bg-slate-50"
                  value={config.commission_rate}
                  onChange={(e) => updateField("commission_rate", parseFloat(e.target.value) || 0)}
                />
                <p className="mt-1 text-[10px] text-slate-500">Decimal (0.3 = 30%)</p>
              </div>
              <div>
                <Label className="text-xs text-slate-600">Monthly close target (per rep)</Label>
                <Input
                  type="number"
                  min="1"
                  className="border-slate-200 bg-slate-50"
                  value={config.monthly_close_target}
                  onChange={(e) => updateField("monthly_close_target", parseInt(e.target.value) || 1)}
                />
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-800">Pipeline aging</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label className="text-xs text-slate-600">Warning after (days)</Label>
                <Input
                  type="number"
                  min="1"
                  className="border-slate-200 bg-slate-50"
                  value={config.aging_days_warning}
                  onChange={(e) => updateField("aging_days_warning", parseInt(e.target.value) || 1)}
                />
              </div>
              <div>
                <Label className="text-xs text-slate-600">Critical after (days)</Label>
                <Input
                  type="number"
                  min="1"
                  className="border-slate-200 bg-slate-50"
                  value={config.aging_days_critical}
                  onChange={(e) => updateField("aging_days_critical", parseInt(e.target.value) || 1)}
                />
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-800">Guarantee & automation</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label className="text-xs text-slate-600">Guarantee period (days)</Label>
                <Input
                  type="number"
                  min="1"
                  className="border-slate-200 bg-slate-50"
                  value={config.guarantee_days}
                  onChange={(e) => updateField("guarantee_days", parseInt(e.target.value) || 1)}
                />
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 bg-slate-50 text-emerald-500"
                  checked={config.auto_assign_enabled}
                  onChange={(e) => updateField("auto_assign_enabled", e.target.checked)}
                />
                <span className="text-sm text-slate-700">Auto-assign new prospects (round-robin)</span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 bg-slate-50 text-emerald-500"
                  checked={config.charlotte_enabled}
                  onChange={(e) => updateField("charlotte_enabled", e.target.checked)}
                />
                <span className="text-sm text-slate-700">Charlotte AI outbound enabled</span>
              </label>
            </div>
          </section>

          <div className="flex justify-end">
            <Button className="bg-emerald-600" onClick={() => void save()} disabled={saving}>
              {saving ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </>
      )}

      <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
        <h2 className="text-sm font-semibold text-slate-800">Integrations</h2>
        <ul className="mt-3 list-inside list-disc space-y-2 text-sm text-slate-600">
          <li>
            <Link href="/crm/charlotte" className="text-emerald-600 hover:underline">
              Charlotte & email webhooks
            </Link>{" "}
            — outbound engagement events into prospect profiles.
          </li>
          <li>
            Backend route <code className="text-slate-600">POST /api/crm/webhooks/email-events</code> with{" "}
            <code className="text-slate-600">X-CRM-Webhook-Secret</code> (see <code className="text-slate-600">backend/.env.example</code>).
          </li>
          <li>
            Prospect scans: <code className="text-slate-600">NEXT_PUBLIC_API_URL</code> +{" "}
            <code className="text-slate-600">/api/crm/run-scan</code> (Next.js) calls your FastAPI scanner.
          </li>
        </ul>
      </section>

      <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
        <h2 className="text-sm font-semibold text-slate-800">Environment checklist</h2>
        <p className="mt-2 text-xs text-slate-600">Set these in Vercel / hosting (frontend) and API host (backend). Values are never shown here.</p>
        <ul className="mt-3 space-y-1 font-mono text-xs text-slate-600">
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

      <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
        <h2 className="text-sm font-semibold text-slate-800">Database</h2>
        <p className="mt-2 text-sm text-slate-600">
          Apply SQL migrations under <code className="text-slate-600">supabase/migrations/</code> in timestamp order in the Supabase project
          that backs this CRM.
        </p>
      </section>
    </div>
  );
}
