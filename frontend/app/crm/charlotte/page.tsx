"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { WebhookInstructions } from "@/components/crm/charlotte/webhook-instructions";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

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
    : "bg-zinc-600";
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
        <h1 className="text-2xl font-semibold text-zinc-50">Charlotte</h1>
        <p className="mt-1 text-sm text-zinc-500">
          AI-powered outbound automation: Apollo lead sourcing, email generation, and Smartlead upload.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Total Runs</div>
          <div className="mt-1 text-xl font-semibold text-zinc-200">{runs.length}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Leads Sourced</div>
          <div className="mt-1 text-xl font-semibold text-sky-400">{totalLeads}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Emails Written</div>
          <div className="mt-1 text-xl font-semibold text-emerald-400">{totalEmails}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Last Run</div>
          <div className="mt-1 flex items-center gap-2">
            <StatusDot status={lastRun?.status} />
            <span className="text-sm text-zinc-300">
              {lastRun?.created_at ? new Date(lastRun.created_at).toLocaleDateString() : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* Tab selector */}
      <div className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 p-1">
        <button
          type="button"
          className={`rounded-md px-4 py-1.5 text-sm font-medium transition ${tab === "runs" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}
          onClick={() => setTab("runs")}
        >
          Run History
        </button>
        <button
          type="button"
          className={`rounded-md px-4 py-1.5 text-sm font-medium transition ${tab === "webhook" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}
          onClick={() => setTab("webhook")}
        >
          Webhook Setup
        </button>
      </div>

      {tab === "runs" ? (
        loading ? (
          <div className="flex justify-center py-12 text-zinc-500">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
          </div>
        ) : runs.length === 0 ? (
          <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-8 text-center text-sm text-zinc-500">
            No Charlotte runs recorded yet. Charlotte runs daily at ~8am MST via cron.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
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
                  <tr key={r.id} className="border-b border-zinc-800/80 hover:bg-zinc-900/40">
                    <td className="px-3 py-2 text-zinc-400">
                      {new Date(r.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <StatusDot status={r.status} />
                        <span className="text-zinc-300">{r.status || "—"}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-zinc-400">{r.industry || "—"}</td>
                    <td className="px-3 py-2 font-medium text-sky-400">{r.leads_pulled ?? "—"}</td>
                    <td className="px-3 py-2 font-medium text-emerald-400">{r.emails_written ?? "—"}</td>
                    <td className="px-3 py-2 text-zinc-300">{r.emails_uploaded ?? "—"}</td>
                    <td className="px-3 py-2 text-zinc-400">
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
