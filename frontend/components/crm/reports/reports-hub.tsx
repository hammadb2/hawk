"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { formatUsd } from "@/lib/crm/format";
import type { ProspectStage } from "@/lib/crm/types";
import { STAGE_META, STAGE_ORDER } from "@/lib/crm/types";

const CLOSED = new Set(["lost", "closed_won"]);

type DateRange = "mtd" | "last30" | "last90" | "ytd" | "all";

const DATE_RANGE_LABELS: Record<DateRange, string> = {
  mtd: "Month to date",
  last30: "Last 30 days",
  last90: "Last 90 days",
  ytd: "Year to date",
  all: "All time",
};

function rangeStartIso(range: DateRange): string | null {
  const d = new Date();
  switch (range) {
    case "mtd":
      d.setDate(1);
      d.setHours(0, 0, 0, 0);
      return d.toISOString();
    case "last30":
      d.setDate(d.getDate() - 30);
      d.setHours(0, 0, 0, 0);
      return d.toISOString();
    case "last90":
      d.setDate(d.getDate() - 90);
      d.setHours(0, 0, 0, 0);
      return d.toISOString();
    case "ytd":
      d.setMonth(0, 1);
      d.setHours(0, 0, 0, 0);
      return d.toISOString();
    case "all":
      return null;
  }
}

function toCsvRow(cells: string[]): string {
  return cells.map((c) => `"${c.replace(/"/g, '""')}"`).join(",");
}

export function ReportsHub() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<DateRange>("mtd");
  const [openPipeline, setOpenPipeline] = useState(0);
  const [clientsInRange, setClientsInRange] = useState(0);
  const [bookedMrrCents, setBookedMrrCents] = useState(0);
  const [pendingCommCents, setPendingCommCents] = useState(0);
  const [funnel, setFunnel] = useState<Record<string, number>>({});
  const [wonLost, setWonLost] = useState({ won: 0, lost: 0 });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const start = rangeStartIso(range);
      const [{ data: prospects, error: e1 }, { data: clients, error: e2 }, commRes] = await Promise.all([
        supabase.from("prospects").select("stage, created_at"),
        supabase.from("clients").select("mrr_cents, status, close_date"),
        supabase.from("crm_commissions").select("amount_cents, status, created_at"),
      ]);

      if (e1) throw e1;
      if (e2) throw e2;

      let commissions = commRes.data ?? [];
      if (commRes.error) {
        const msg = commRes.error.message ?? "";
        if (msg.includes("crm_commissions") || msg.includes("does not exist") || commRes.error.code === "PGRST205") {
          commissions = [];
        } else throw commRes.error;
      }

      const plist = prospects ?? [];
      let open = 0;
      const byStage: Record<string, number> = {};
      for (const s of STAGE_ORDER) byStage[s] = 0;
      let won = 0;
      let lost = 0;
      for (const p of plist) {
        if (start && (p.created_at as string) < start) continue;
        const st = p.stage as string;
        byStage[st] = (byStage[st] ?? 0) + 1;
        if (!CLOSED.has(st)) open += 1;
        if (st === "closed_won") won += 1;
        if (st === "lost") lost += 1;
      }

      let inRange = 0;
      let mrr = 0;
      for (const c of clients ?? []) {
        if (!start || (c.close_date as string) >= start) inRange += 1;
        if (c.status === "active") mrr += (c.mrr_cents as number) ?? 0;
      }

      let pend = 0;
      for (const x of commissions) {
        if (start && (x.created_at as string) < start) continue;
        if (x.status === "pending") pend += (x.amount_cents as number) ?? 0;
      }

      setOpenPipeline(open);
      setClientsInRange(inRange);
      setBookedMrrCents(mrr);
      setPendingCommCents(pend);
      setFunnel(byStage);
      setWonLost({ won, lost });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }, [supabase, range]);

  useEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  function exportCsv() {
    const rows = [
      toCsvRow(["Metric", "Value"]),
      toCsvRow(["Date range", DATE_RANGE_LABELS[range]]),
      toCsvRow(["Open pipeline", String(openPipeline)]),
      toCsvRow(["New clients", String(clientsInRange)]),
      toCsvRow(["Booked MRR (active)", formatUsd(bookedMrrCents)]),
      toCsvRow(["Pending commission", formatUsd(pendingCommCents)]),
      toCsvRow(["Won", String(wonLost.won)]),
      toCsvRow(["Lost", String(wonLost.lost)]),
      "",
      toCsvRow(["Stage", "Count"]),
      ...STAGE_ORDER.map((st) => toCsvRow([STAGE_META[st as ProspectStage].label, String(funnel[st] ?? 0)])),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `hawk-crm-report-${range}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  const totalDecided = wonLost.won + wonLost.lost;
  const winRatePct = totalDecided > 0 ? Math.round((wonLost.won / totalDecided) * 100) : null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          <select
            value={range}
            onChange={(e) => setRange(e.target.value as DateRange)}
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700 focus:border-emerald-500 focus:outline-none"
          >
            {(Object.keys(DATE_RANGE_LABELS) as DateRange[]).map((k) => (
              <option key={k} value={k}>{DATE_RANGE_LABELS[k]}</option>
            ))}
          </select>
          <p className="text-sm text-slate-600">
            Numbers respect your role: team leads see their pod; executives see the full org.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            onClick={exportCsv}
          >
            Export CSV
          </button>
          <button
            type="button"
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            onClick={() => void load()}
          >
            Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-slate-600">Loading…</div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Open pipeline</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">{openPipeline}</div>
              <p className="mt-1 text-xs text-slate-500">Prospects not lost / won</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">New clients</div>
              <div className="mt-1 text-2xl font-semibold text-sky-400">{clientsInRange}</div>
              <p className="mt-1 text-xs text-slate-500">In selected date range</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Booked MRR (active)</div>
              <div className="mt-1 text-2xl font-semibold text-emerald-600">{formatUsd(bookedMrrCents)}</div>
              <p className="mt-1 text-xs text-slate-500">Sum of active client subscriptions</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Pending commission</div>
              <div className="mt-1 text-2xl font-semibold text-amber-300">{formatUsd(pendingCommCents)}</div>
              <p className="mt-1 text-xs text-slate-500">Payroll not marked paid</p>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-4">
              <h2 className="text-sm font-semibold text-slate-800">Pipeline funnel</h2>
              <p className="mt-0.5 text-xs text-slate-600">Prospect count by stage ({DATE_RANGE_LABELS[range].toLowerCase()})</p>
              <ul className="mt-4 space-y-2">
                {STAGE_ORDER.map((st) => {
                  const n = funnel[st] ?? 0;
                  const label = STAGE_META[st as ProspectStage].label;
                  const max = Math.max(1, ...STAGE_ORDER.map((s) => funnel[s] ?? 0));
                  const pct = Math.round((n / max) * 100);
                  return (
                    <li key={st} className="flex items-center gap-3 text-sm">
                      <span className="w-28 shrink-0 text-slate-600">{label}</span>
                      <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${pct}%`, backgroundColor: STAGE_META[st as ProspectStage].color }}
                        />
                      </div>
                      <span className="w-8 text-right font-mono text-slate-700">{n}</span>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-4">
              <h2 className="text-sm font-semibold text-slate-800">Outcomes</h2>
              <p className="mt-0.5 text-xs text-slate-600">Won vs lost in {DATE_RANGE_LABELS[range].toLowerCase()}</p>
              <dl className="mt-4 space-y-3 text-sm">
                <div className="flex justify-between border-b border-slate-200/90 pb-2">
                  <dt className="text-slate-600">Marked closed won</dt>
                  <dd className="font-medium text-emerald-600">{wonLost.won}</dd>
                </div>
                <div className="flex justify-between border-b border-slate-200/90 pb-2">
                  <dt className="text-slate-600">Marked lost</dt>
                  <dd className="font-medium text-rose-400">{wonLost.lost}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-600">Win rate (won / decided)</dt>
                  <dd className="font-medium text-slate-800">{winRatePct != null ? `${winRatePct}%` : "—"}</dd>
                </div>
              </dl>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
