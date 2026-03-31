"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { formatUsd } from "@/lib/crm/format";
import type { ProspectStage } from "@/lib/crm/types";
import { STAGE_META, STAGE_ORDER } from "@/lib/crm/types";

const CLOSED = new Set(["lost", "closed_won"]);

function monthStartIso(): string {
  const d = new Date();
  d.setDate(1);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

export function ReportsHub() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [loading, setLoading] = useState(true);
  const [openPipeline, setOpenPipeline] = useState(0);
  const [clientsMtd, setClientsMtd] = useState(0);
  const [bookedMrrCents, setBookedMrrCents] = useState(0);
  const [pendingCommCents, setPendingCommCents] = useState(0);
  const [funnel, setFunnel] = useState<Record<string, number>>({});
  const [wonLost, setWonLost] = useState({ won: 0, lost: 0 });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const start = monthStartIso();
      const [{ data: prospects, error: e1 }, { data: clients, error: e2 }, commRes] = await Promise.all([
        supabase.from("prospects").select("stage"),
        supabase.from("clients").select("mrr_cents, status, close_date"),
        supabase.from("crm_commissions").select("amount_cents, status"),
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
        const st = p.stage as string;
        byStage[st] = (byStage[st] ?? 0) + 1;
        if (!CLOSED.has(st)) open += 1;
        if (st === "closed_won") won += 1;
        if (st === "lost") lost += 1;
      }

      let mtd = 0;
      let mrr = 0;
      for (const c of clients ?? []) {
        if ((c.close_date as string) >= start) mtd += 1;
        if (c.status === "active") mrr += (c.mrr_cents as number) ?? 0;
      }

      let pend = 0;
      for (const x of commissions) {
        if (x.status === "pending") pend += (x.amount_cents as number) ?? 0;
      }

      setOpenPipeline(open);
      setClientsMtd(mtd);
      setBookedMrrCents(mrr);
      setPendingCommCents(pend);
      setFunnel(byStage);
      setWonLost({ won, lost });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }, [supabase]);

  useEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
      </div>
    );
  }

  const totalDecided = wonLost.won + wonLost.lost;
  const winRatePct = totalDecided > 0 ? Math.round((wonLost.won / totalDecided) * 100) : null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-zinc-500">
          Numbers respect your role: team leads see their pod; executives see the full org.
        </p>
        <button
          type="button"
          className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-900"
          onClick={() => void load()}
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="py-16 text-center text-zinc-500">Loading…</div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Open pipeline</div>
              <div className="mt-1 text-2xl font-semibold text-zinc-100">{openPipeline}</div>
              <p className="mt-1 text-xs text-zinc-600">Prospects not lost / won</p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">New clients (MTD)</div>
              <div className="mt-1 text-2xl font-semibold text-sky-400">{clientsMtd}</div>
              <p className="mt-1 text-xs text-zinc-600">Client records created this month</p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Booked MRR (active)</div>
              <div className="mt-1 text-2xl font-semibold text-emerald-400">{formatUsd(bookedMrrCents)}</div>
              <p className="mt-1 text-xs text-zinc-600">Sum of active client subscriptions</p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Pending commission</div>
              <div className="mt-1 text-2xl font-semibold text-amber-300">{formatUsd(pendingCommCents)}</div>
              <p className="mt-1 text-xs text-zinc-600">Payroll not marked paid</p>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <h2 className="text-sm font-semibold text-zinc-200">Pipeline funnel</h2>
              <p className="mt-0.5 text-xs text-zinc-500">Prospect count by stage (visible scope)</p>
              <ul className="mt-4 space-y-2">
                {STAGE_ORDER.map((st) => {
                  const n = funnel[st] ?? 0;
                  const label = STAGE_META[st as ProspectStage].label;
                  const max = Math.max(1, ...STAGE_ORDER.map((s) => funnel[s] ?? 0));
                  const pct = Math.round((n / max) * 100);
                  return (
                    <li key={st} className="flex items-center gap-3 text-sm">
                      <span className="w-28 shrink-0 text-zinc-500">{label}</span>
                      <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-zinc-800">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${pct}%`, backgroundColor: STAGE_META[st as ProspectStage].color }}
                        />
                      </div>
                      <span className="w-8 text-right font-mono text-zinc-300">{n}</span>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <h2 className="text-sm font-semibold text-zinc-200">Outcomes (prospects)</h2>
              <p className="mt-0.5 text-xs text-zinc-500">Won vs lost cards still in pipeline data</p>
              <dl className="mt-4 space-y-3 text-sm">
                <div className="flex justify-between border-b border-zinc-800/80 pb-2">
                  <dt className="text-zinc-500">Marked closed won</dt>
                  <dd className="font-medium text-emerald-400">{wonLost.won}</dd>
                </div>
                <div className="flex justify-between border-b border-zinc-800/80 pb-2">
                  <dt className="text-zinc-500">Marked lost</dt>
                  <dd className="font-medium text-rose-400">{wonLost.lost}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500">Win rate (won / decided)</dt>
                  <dd className="font-medium text-zinc-200">{winRatePct != null ? `${winRatePct}%` : "—"}</dd>
                </div>
              </dl>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
