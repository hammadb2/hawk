"use client";

import { useEffect, useState } from "react";
import { readApiErrorResponse } from "@/lib/crm/api-error";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { createClient } from "@/lib/supabase/client";

type CharlotteRun = {
  id?: string;
  created_at?: string;
  leads_pulled?: number;
  emails_written?: number;
  emails_uploaded?: number;
  status?: string;
  error_summary?: string;
  duration_seconds?: number;
};

type ScannerHealth = {
  id?: string;
  checked_at?: string;
  status?: string;
  queue_depth?: number;
  avg_scan_seconds?: number;
  failures_1h?: number;
};

type HealthData = {
  ok: boolean;
  charlotte_last_run: CharlotteRun | null;
  replies_unhandled: number;
  scanner_health_last: ScannerHealth | null;
};

function StatusBadge({ status }: { status: string | undefined }) {
  const s = (status || "unknown").toLowerCase();
  const color =
    s === "ok" || s === "success" || s === "complete"
      ? "bg-emerald-50 text-emerald-600 border-emerald-700"
      : s === "degraded" || s === "warning" || s === "partial"
        ? "bg-amber-900/50 text-amber-400 border-amber-700"
        : s === "failed" || s === "error"
          ? "bg-rose-900/50 text-rose-400 border-rose-700"
          : "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${color}`}>
      {status || "unknown"}
    </span>
  );
}

function timeAgo(iso: string | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function CrmHealthPage() {
  const supabase = createClient();
  const [data, setData] = useState<HealthData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setErr("Sign in required");
        setLoading(false);
        return;
      }
      const res = await fetch(`${CRM_API_BASE_URL}/api/crm/health-dashboard`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!res.ok) {
        setErr(await readApiErrorResponse(res));
        setLoading(false);
        return;
      }
      const j = await res.json();
      if (!cancelled) {
        setData(j as HealthData);
        setLoading(false);
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [supabase]);

  const charlotte = data?.charlotte_last_run;
  const scanner = data?.scanner_health_last;
  const repliesUnhandled = data?.replies_unhandled ?? 0;

  const replyColor =
    repliesUnhandled === 0
      ? "text-emerald-600"
      : repliesUnhandled <= 5
        ? "text-amber-400"
        : "text-rose-400";

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">System Health</h1>
        <p className="mt-1 text-sm text-slate-600">Live status of Charlotte, scanner infrastructure, and reply queue.</p>
      </div>

      {err && <p className="text-sm text-rose-400">{err}</p>}

      {loading ? (
        <div className="flex justify-center py-16 text-slate-600">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
        </div>
      ) : data ? (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Charlotte</div>
                <StatusBadge status={charlotte?.status} />
              </div>
              <div className="mt-2 text-sm text-slate-600">
                Last run: {timeAgo(charlotte?.created_at)}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Scanner</div>
                <StatusBadge status={scanner?.status} />
              </div>
              <div className="mt-2 text-sm text-slate-600">
                Last check: {timeAgo(scanner?.checked_at)}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Reply Queue</div>
              <div className={`mt-2 text-2xl font-semibold ${replyColor}`}>{repliesUnhandled}</div>
              <div className="text-xs text-slate-500">unhandled replies</div>
            </div>
          </div>

          {/* Charlotte detail */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
            <h2 className="text-sm font-semibold text-slate-800">Charlotte — Last Run Details</h2>
            {charlotte ? (
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Status</dt>
                  <dd><StatusBadge status={charlotte.status} /></dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Run time</dt>
                  <dd className="text-slate-700">
                    {charlotte.created_at ? new Date(charlotte.created_at).toLocaleString() : "—"}
                  </dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Leads pulled</dt>
                  <dd className="font-medium text-slate-800">{charlotte.leads_pulled ?? "—"}</dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Emails written</dt>
                  <dd className="font-medium text-slate-800">{charlotte.emails_written ?? "—"}</dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Emails uploaded</dt>
                  <dd className="font-medium text-slate-800">{charlotte.emails_uploaded ?? "—"}</dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Duration</dt>
                  <dd className="text-slate-700">
                    {charlotte.duration_seconds != null ? `${charlotte.duration_seconds}s` : "—"}
                  </dd>
                </div>
                {charlotte.error_summary && (
                  <div className="col-span-2">
                    <dt className="text-slate-600">Error</dt>
                    <dd className="mt-1 rounded border border-rose-800/50 bg-rose-950/30 p-2 text-xs text-rose-300">
                      {charlotte.error_summary}
                    </dd>
                  </div>
                )}
              </dl>
            ) : (
              <p className="mt-3 text-sm text-slate-600">No Charlotte runs recorded yet.</p>
            )}
          </div>

          {/* Scanner detail */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
            <h2 className="text-sm font-semibold text-slate-800">Scanner Infrastructure</h2>
            {scanner ? (
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Status</dt>
                  <dd><StatusBadge status={scanner.status} /></dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Last check</dt>
                  <dd className="text-slate-700">
                    {scanner.checked_at ? new Date(scanner.checked_at).toLocaleString() : "—"}
                  </dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Queue depth</dt>
                  <dd className="font-medium text-slate-800">{scanner.queue_depth ?? "—"}</dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Avg scan time</dt>
                  <dd className="text-slate-700">
                    {scanner.avg_scan_seconds != null ? `${scanner.avg_scan_seconds}s` : "—"}
                  </dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/80 pb-2">
                  <dt className="text-slate-600">Failures (1h)</dt>
                  <dd className={`font-medium ${(scanner.failures_1h ?? 0) > 0 ? "text-rose-400" : "text-slate-800"}`}>
                    {scanner.failures_1h ?? "—"}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="mt-3 text-sm text-slate-600">No scanner health logs recorded yet.</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
