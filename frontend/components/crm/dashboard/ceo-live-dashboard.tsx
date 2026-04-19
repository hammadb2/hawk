"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { CrmActivityRow, Profile } from "@/lib/crm/types";
import { fetchCrmDashboardKpis } from "@/lib/crm/dashboard-kpis";

type Kpis = {
  emailsSentToday: number;
  emailRepliesToday: number;
  callsBookedToday: number;
  closesMtd: number;
  pipelineOpenDollars: number;
  stale48h: number;
  activeMrrCents: number;
};

type LeaderRow = { repId: string; name: string; closes: number; mrrCents: number };

type RepHealthRow = { repId: string; name: string; healthScore: number | null };

function localStartOfDayIso(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function localStartOfMonthIso(): string {
  const d = new Date();
  d.setDate(1);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

export function CeoLiveDashboard({
  supabase,
  profile,
  accessToken,
}: {
  supabase: SupabaseClient;
  profile: Profile;
  accessToken: string | null;
}) {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderRow[]>([]);
  const [activities, setActivities] = useState<CrmActivityRow[]>([]);
  const [activityFilter, setActivityFilter] = useState<string>("all");
  const [prospectLabels, setProspectLabels] = useState<Record<string, string>>({});
  const [repHealth, setRepHealth] = useState<RepHealthRow[]>([]);

  const loadAll = useCallback(async () => {
    const startDay = localStartOfDayIso();
    const startMonth = localStartOfMonthIso();

    const [actRes, clientsRes, healthRes, kpiPayload] = await Promise.all([
      supabase
        .from("activities")
        .select("id,prospect_id,type,notes,metadata,created_by,created_at")
        .order("created_at", { ascending: false })
        .limit(80),
      supabase.from("clients").select("id,closing_rep_id,mrr_cents,close_date,status").eq("status", "active").limit(500),
      supabase
        .from("profiles")
        .select("id,full_name,email,health_score,role")
        .in("role", ["sales_rep", "closer", "team_lead"])
        .limit(100),
      accessToken
        ? fetchCrmDashboardKpis(accessToken, startDay, startMonth).catch((e) => {
            console.error("[CEO dashboard] KPI API failed:", e);
            return null;
          })
        : Promise.resolve(null),
    ]);

    const acts = (actRes.data ?? []) as CrmActivityRow[];
    setActivities(acts);

    if (kpiPayload) {
      setKpis({
        emailsSentToday: kpiPayload.emails_sent_today,
        emailRepliesToday: kpiPayload.emails_replied_today,
        callsBookedToday: kpiPayload.calls_booked_today,
        closesMtd: kpiPayload.closes_mtd,
        pipelineOpenDollars: kpiPayload.pipeline_open_dollars,
        stale48h: kpiPayload.stale_48h_open,
        activeMrrCents: kpiPayload.mrr_total_cents,
      });
    } else {
      const clients = clientsRes.data ?? [];
      setKpis({
        emailsSentToday: 0,
        emailRepliesToday: 0,
        callsBookedToday: 0,
        closesMtd: clients.filter((c) => c.close_date && c.close_date >= startMonth).length,
        pipelineOpenDollars: 0,
        stale48h: 0,
        activeMrrCents: clients.reduce((s, c) => s + (c.mrr_cents ?? 0), 0),
      });
    }

    const prospectIds = Array.from(
      new Set(acts.map((a) => a.prospect_id).filter((x): x is string => typeof x === "string" && !!x))
    );
    if (prospectIds.length) {
      const { data: pl } = await supabase
        .from("prospects")
        .select("id,company_name,domain")
        .in("id", prospectIds);
      const map: Record<string, string> = {};
      for (const row of pl ?? []) {
        map[row.id] = (row.company_name as string | null) || (row.domain as string) || row.id.slice(0, 8);
      }
      setProspectLabels(map);
    } else {
      setProspectLabels({});
    }

    const clients = clientsRes.data ?? [];
    const mtdClients = clients.filter((c) => c.close_date && c.close_date >= startMonth && c.closing_rep_id);
    const byRep = new Map<string, { closes: number; mrrCents: number }>();
    for (const c of mtdClients) {
      const rid = c.closing_rep_id as string;
      const cur = byRep.get(rid) ?? { closes: 0, mrrCents: 0 };
      cur.closes += 1;
      cur.mrrCents += c.mrr_cents ?? 0;
      byRep.set(rid, cur);
    }
    const repIds = Array.from(byRep.keys());
    if (repIds.length === 0) {
      setLeaderboard([]);
    } else {
      const profRes = await supabase.from("profiles").select("id,full_name,email").in("id", repIds);
      const profs = profRes.data ?? [];
      const nameById = new Map(profs.map((p) => [p.id, p.full_name || p.email || p.id]));
      setLeaderboard(
        repIds
          .map((id) => ({
            repId: id,
            name: nameById.get(id) ?? id,
            closes: byRep.get(id)?.closes ?? 0,
            mrrCents: byRep.get(id)?.mrrCents ?? 0,
          }))
          .sort((a, b) => b.mrrCents - a.mrrCents)
      );
    }

    const hpRows = (healthRes.data ?? []) as {
      id: string;
      full_name: string | null;
      email: string | null;
      health_score: number | null;
    }[];
    setRepHealth(
      hpRows
        .map((r) => ({
          repId: r.id,
          name: r.full_name || r.email || r.id.slice(0, 8),
          healthScore: typeof r.health_score === "number" ? r.health_score : null,
        }))
        .sort((a, b) => {
          const av = a.healthScore ?? -1;
          const bv = b.healthScore ?? -1;
          return av - bv;
        })
    );
  }, [supabase, accessToken]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    const ch = supabase
      .channel("ceo-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "activities" }, () => {
        void loadAll();
      })
      .on("postgres_changes", { event: "*", schema: "public", table: "prospects" }, () => {
        void loadAll();
      })
      .subscribe();
    return () => {
      void supabase.removeChannel(ch);
    };
  }, [supabase, loadAll]);

  const filteredActivities = useMemo(() => {
    if (activityFilter === "all") return activities;
    return activities.filter((a) => a.type === activityFilter);
  }, [activities, activityFilter]);

  const prospectLabel = useCallback(
    (pid: string | null) => {
      if (!pid) return "—";
      return prospectLabels[pid] ?? pid.slice(0, 8);
    },
    [prospectLabels],
  );

  if (!kpis) {
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      </div>
    );
  }

  const roleNote = profile.role === "hos" ? "HoS" : "CEO";

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/90 p-4">
        <h2 className="text-sm font-semibold text-emerald-900">Live ops ({roleNote})</h2>
        <p className="mt-1 text-xs text-slate-600">
          KPIs use your browser&apos;s local calendar day. Pipeline $ uses the same hawk-score bands as the Kanban. Activity feed updates in real time.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Emails logged today" value={kpis.emailsSentToday} />
        <KpiCard label="Replies today" value={kpis.emailRepliesToday} />
        <KpiCard label="Calls booked today" value={kpis.callsBookedToday} />
        <KpiCard label="Closes (MTD)" value={kpis.closesMtd} />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <KpiCard label="Open pipeline ($ est.)" value={`$${kpis.pipelineOpenDollars.toLocaleString()}`} />
        <KpiCard label="Stale 48h+ (open)" value={kpis.stale48h} hint="Any open stage, no activity 48h+" />
        <KpiCard label="Active client MRR" value={`$${(kpis.activeMrrCents / 100).toLocaleString()}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-medium text-slate-800">Rep leaderboard (MTD)</h3>
          <p className="text-xs text-slate-600">By revenue closed this month</p>
          <ul className="mt-3 space-y-2 text-sm">
            {leaderboard.length === 0 && <li className="text-slate-600">No closes recorded this month yet.</li>}
            {leaderboard.map((row, i) => (
              <li key={row.repId} className="flex justify-between gap-2 text-slate-700">
                <span>
                  {i + 1}. {row.name}
                </span>
                <span className="text-slate-600">
                  {row.closes} deal{row.closes === 1 ? "" : "s"} · ${(row.mrrCents / 100).toLocaleString()} MRR
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-medium text-slate-800">Rep health (0–100)</h3>
          <p className="text-xs text-slate-600">Daily score from pipeline hygiene; under 50 alerts CEO via WhatsApp when configured.</p>
          <ul className="mt-3 max-h-[220px] space-y-2 overflow-y-auto text-sm">
            {repHealth.length === 0 && <li className="text-slate-600">No sales roles loaded.</li>}
            {repHealth.map((row) => (
              <li key={row.repId} className="flex justify-between gap-2 text-slate-700">
                <span>{row.name}</span>
                <span
                  className={
                    row.healthScore !== null && row.healthScore < 50
                      ? "font-medium text-rose-600"
                      : "text-slate-600"
                  }
                >
                  {row.healthScore ?? "—"}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-medium text-slate-800">Quick links</h3>
          <ul className="mt-3 space-y-2 text-sm">
            <li>
              <Link href="/crm/pipeline" className="text-emerald-600 hover:underline">
                Pipeline
              </Link>
            </li>
            <li>
              <Link href="/crm/settings" className="text-emerald-600 hover:underline">
                Settings &amp; monitor history
              </Link>
            </li>
          </ul>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-slate-800">Activity feed</h3>
          <select
            value={activityFilter}
            onChange={(e) => setActivityFilter(e.target.value)}
            className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-800"
          >
            <option value="all">All types</option>
            <option value="stage_changed">Stage changes</option>
            <option value="note">Notes</option>
            <option value="call">Calls</option>
          </select>
        </div>
        <ul className="mt-3 max-h-[420px] space-y-2 overflow-y-auto text-sm">
          {filteredActivities.map((a) => (
            <li key={a.id} className="rounded-lg border border-slate-200/90 bg-white shadow-sm px-3 py-2">
              <div className="flex flex-wrap justify-between gap-2 text-slate-600">
                <span className="text-emerald-600/90">{a.type}</span>
                <span className="text-xs">{new Date(a.created_at).toLocaleString()}</span>
              </div>
              <div className="mt-1 text-slate-700">
                {a.prospect_id ? (
                  <Link href={`/crm/prospects/${a.prospect_id}`} className="hover:text-emerald-600 hover:underline">
                    {prospectLabel(a.prospect_id)}
                  </Link>
                ) : (
                  "—"
                )}
              </div>
              {a.type === "stage_changed" && a.metadata && (
                <p className="mt-1 text-xs text-slate-600">
                  {(a.metadata as { from?: string; to?: string }).from} → {(a.metadata as { to?: string }).to}
                </p>
              )}
              {a.notes && <p className="mt-1 text-xs text-slate-600">{a.notes}</p>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function KpiCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-600">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}
