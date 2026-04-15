"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { DomainHealth, CampaignPreflight } from "@/lib/crm/types";

const PREFLIGHT_CHECKS = [
  { key: "dns_verified", label: "DNS records verified (SPF, DKIM, DMARC)" },
  { key: "warmup_threshold", label: "All domains past warmup threshold" },
  { key: "bounce_rate_ok", label: "Bounce rate below 3% on all domains" },
  { key: "content_reviewed", label: "Email content reviewed for compliance" },
  { key: "suppression_updated", label: "Suppression list updated" },
  { key: "reply_handling", label: "Reply handling flow tested" },
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function CampaignHealthPage() {
  const supabase = createClient();
  const { authReady, session, profile } = useCrmAuth();
  const [domains, setDomains] = useState<DomainHealth[]>([]);
  const [preflight, setPreflight] = useState<CampaignPreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checks, setChecks] = useState<Record<string, boolean>>({});

  /* add domain form */
  const [showAdd, setShowAdd] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [dhRes, pfRes] = await Promise.all([
      supabase.from("domain_health").select("*").order("domain"),
      supabase.from("campaign_preflight").select("*").eq("check_date", todayIso()).order("created_at", { ascending: false }).limit(1),
    ]);
    setDomains((dhRes.data ?? []) as DomainHealth[]);
    const pf = ((pfRes.data ?? [])[0] as CampaignPreflight) ?? null;
    setPreflight(pf);
    setChecks(pf?.checks ?? {});
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  async function saveChecklist() {
    if (!profile) return;
    setSaving(true);
    const allGood = PREFLIGHT_CHECKS.every((c) => checks[c.key]);
    if (preflight) {
      await supabase.from("campaign_preflight").update({ checks, go_status: allGood }).eq("id", preflight.id);
    } else {
      await supabase.from("campaign_preflight").insert({
        check_date: todayIso(),
        checks,
        completed_by: profile.id,
        go_status: allGood,
      });
    }
    toast.success(allGood ? "All clear — GO!" : "Checklist saved (not all clear)");
    void load();
    setSaving(false);
  }

  async function addDomain() {
    if (!newDomain.trim()) return;
    setAdding(true);
    const { error } = await supabase.from("domain_health").insert({
      domain: newDomain.trim().toLowerCase(),
      status: "warming",
    });
    if (error) toast.error(error.message);
    else {
      toast.success("Domain added");
      setNewDomain("");
      setShowAdd(false);
      void load();
    }
    setAdding(false);
  }

  async function updateDomainStatus(id: string, status: string) {
    const { error } = await supabase.from("domain_health").update({ status, updated_at: new Date().toISOString() }).eq("id", id);
    if (error) toast.error(error.message);
    else void load();
  }

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  const statusColor: Record<string, string> = {
    active: "text-emerald-600",
    warming: "text-amber-500",
    paused: "text-slate-400",
    flagged: "text-rose-600",
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Campaign Health</h1>
        <p className="mt-1 text-sm text-slate-600">Domain health tracker and pre-send checklist.</p>
      </div>

      {/* Pre-flight checklist */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">Pre-Flight Checklist — {todayIso()}</h2>
          {preflight?.go_status && (
            <span className="rounded-full bg-emerald-100 px-3 py-0.5 text-xs font-medium text-emerald-800">GO</span>
          )}
        </div>
        <div className="space-y-2">
          {PREFLIGHT_CHECKS.map((c) => (
            <label key={c.key} className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={!!checks[c.key]}
                onChange={(e) => setChecks((prev) => ({ ...prev, [c.key]: e.target.checked }))}
                className="rounded border-slate-300"
              />
              {c.label}
            </label>
          ))}
        </div>
        <button
          type="button"
          disabled={saving}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          onClick={() => void saveChecklist()}
        >
          {saving ? "Saving…" : "Save Checklist"}
        </button>
      </div>

      {/* Domain health table */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">Domain Health</h2>
          <button
            type="button"
            className="text-sm text-emerald-600 hover:underline"
            onClick={() => setShowAdd(!showAdd)}
          >
            {showAdd ? "Cancel" : "+ Add Domain"}
          </button>
        </div>

        {showAdd && (
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              placeholder="e.g. send1.example.com"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
            />
            <button
              type="button"
              disabled={adding}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              onClick={() => void addDomain()}
            >
              {adding ? "Adding…" : "Add"}
            </button>
          </div>
        )}

        {loading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : domains.length === 0 ? (
          <p className="text-sm text-slate-500">No domains tracked yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-600">
                <tr>
                  <th className="px-2 py-1">Domain</th>
                  <th className="px-2 py-1">Warmup Day</th>
                  <th className="px-2 py-1">Daily Sends</th>
                  <th className="px-2 py-1">Bounce Rate</th>
                  <th className="px-2 py-1">Status</th>
                  <th className="px-2 py-1">Actions</th>
                </tr>
              </thead>
              <tbody>
                {domains.map((d) => (
                  <tr key={d.id} className="border-b border-slate-100">
                    <td className="px-2 py-1 font-medium text-slate-800">{d.domain}</td>
                    <td className="px-2 py-1">{d.warmup_day}</td>
                    <td className="px-2 py-1">{d.daily_sends}</td>
                    <td className="px-2 py-1">
                      <span className={d.bounce_rate > 3 ? "text-rose-600 font-medium" : ""}>
                        {d.bounce_rate.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-2 py-1">
                      <span className={`font-medium ${statusColor[d.status] ?? ""}`}>
                        {d.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-2 py-1">
                      <select
                        className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700"
                        value={d.status}
                        onChange={(e) => void updateDomainStatus(d.id, e.target.value)}
                      >
                        <option value="active">Active</option>
                        <option value="warming">Warming</option>
                        <option value="paused">Paused</option>
                        <option value="flagged">Flagged</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
