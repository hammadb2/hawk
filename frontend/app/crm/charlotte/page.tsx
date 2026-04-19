"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { WebhookInstructions } from "@/components/crm/charlotte/webhook-instructions";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import {
  crmEmptyState,
  crmPageSubtitle,
  crmPageTitle,
  crmSurfaceCard,
  crmTableRow,
  crmTableThead,
  crmTableWrap,
} from "@/lib/crm/crm-surface";

type CharlotteRunRow = {
  id: string;
  created_at: string;
  status?: string;
  leads_pulled?: number;
  emails_written?: number;
  emails_uploaded?: number;
  duration_seconds?: number;
  error_summary?: string;
  industry?: string;
  run_type?: string;
};

function StatusDot({ status }: { status: string | undefined }) {
  const s = (status || "").toLowerCase();
  const color =
    s === "success" || s === "complete" ? "bg-emerald-500"
    : s === "partial" || s === "warning" ? "bg-amber-500"
    : s === "failed" || s === "error" ? "bg-rose-500"
    : "bg-slate-400";
  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} />;
}

export default function CharlottePage() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [runs, setRuns] = useState<CharlotteRunRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"runs" | "webhook">("runs");

  const loadRuns = useCallback(async () => {
    if (!session?.access_token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${CRM_API_BASE_URL}/api/crm/charlotte-runs`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        const j = await res.json();
        setRuns((j.runs ?? []) as CharlotteRunRow[]);
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [session?.access_token]);

  useEffect(() => {
    if (authReady && session && profile) void loadRuns();
  }, [authReady, session, profile, loadRuns]);

  const totalLeads = runs.reduce((s, r) => s + (r.leads_pulled ?? 0), 0);
  const totalEmails = runs.reduce((s, r) => s + (r.emails_written ?? 0), 0);
  const lastRun = runs[0];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className={crmPageTitle}>Charlotte</h1>
        <p className={crmPageSubtitle}>
          AI-powered outbound automation: Apollo lead sourcing, email generation, and Smartlead upload.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-3 sm:grid-cols-4">
        <div className={`px-4 py-3 ${crmSurfaceCard}`}>
          <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Total Runs</div>
          <div className="mt-1 text-xl font-semibold text-white">{runs.length}</div>
        </div>
        <div className={`px-4 py-3 ${crmSurfaceCard}`}>
          <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Leads Sourced</div>
          <div className="mt-1 text-xl font-semibold text-sky-400">{totalLeads}</div>
        </div>
        <div className={`px-4 py-3 ${crmSurfaceCard}`}>
          <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Emails Written</div>
          <div className="mt-1 text-xl font-semibold text-emerald-400">{totalEmails}</div>
        </div>
        <div className={`px-4 py-3 ${crmSurfaceCard}`}>
          <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Last Run</div>
          <div className="mt-1 flex items-center gap-2">
            <StatusDot status={lastRun?.status} />
            <span className="text-sm text-slate-300">
              {lastRun?.created_at ? new Date(lastRun.created_at).toLocaleDateString() : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* Tab selector */}
      <div className="flex gap-1 rounded-xl border border-[#1e1e2e] bg-[#0d0d14] p-1">
        <button
          type="button"
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${tab === "runs" ? "bg-[#1a1a24] text-white" : "text-slate-500 hover:text-slate-300"}`}
          onClick={() => setTab("runs")}
        >
          Run History
        </button>
        <button
          type="button"
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${tab === "webhook" ? "bg-[#1a1a24] text-white" : "text-slate-500 hover:text-slate-300"}`}
          onClick={() => setTab("webhook")}
        >
          Webhook Setup
        </button>
      </div>

      {tab === "runs" ? (
        loading ? (
          <div className="flex justify-center py-12 text-slate-600">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
          </div>
        ) : runs.length === 0 ? (
          <p className={crmEmptyState}>
            No Charlotte runs recorded yet. Charlotte runs daily at ~8am MST via cron.
          </p>
        ) : (
          <div className={crmTableWrap}>
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className={crmTableThead}>
                <tr>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Industry</th>
                  <th className="px-3 py-2">Leads</th>
                  <th className="px-3 py-2">Emails</th>
                  <th className="px-3 py-2">Uploaded</th>
                  <th className="px-3 py-2">Duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className={crmTableRow}>
                    <td className="px-3 py-2 text-slate-400">
                      {new Date(r.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <StatusDot status={r.status} />
                        <span className="text-slate-200">{r.status || "—"}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-slate-400">{r.industry || "—"}</td>
                    <td className="px-3 py-2 font-medium text-sky-400">{r.leads_pulled ?? "—"}</td>
                    <td className="px-3 py-2 font-medium text-emerald-400">{r.emails_written ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-300">{r.emails_uploaded ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-400">
                      {r.duration_seconds != null ? `${r.duration_seconds}s` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        <WebhookInstructions apiBase={CRM_API_BASE_URL} />
      )}
    </div>
  );
}
