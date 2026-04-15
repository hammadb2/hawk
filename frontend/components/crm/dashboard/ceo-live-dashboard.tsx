"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { CrmActivityRow, Prospect, Profile } from "@/lib/crm/types";
import { sumOpenPipelineValueDollars } from "@/lib/crm/pipeline-value";

type Kpis = {
  emailsSentToday: number;
  emailRepliesToday: number;
  callsBookedToday: number;
  closesMtd: number;
  pipelineOpenDollars: number;
  stale48h: number;
  activeMrrCents: number;
  /* VA ops */
  vaCallsBookedToday: number;
  vaEmailsSentToday: number;
  vaReplyRate: number;
  vaStandings: { green: number; yellow: number; red: number };
  vaActiveAlerts: number;
};

type LeaderRow = { repId: string; name: string; closes: number; mrrCents: number };

type RepHealthRow = { repId: string; name: string; healthScore: number | null };

type VaStandingSummary = { green: number; yellow: number; red: number };

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
}: {
  supabase: SupabaseClient;
  profile: Profile;
}) {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderRow[]>([]);
  const [activities, setActivities] = useState<CrmActivityRow[]>([]);
  const [activityFilter, setActivityFilter] = useState<string>("all");
  const [prospectsCache, setProspectsCache] = useState<Prospect[]>([]);
  const [repHealth, setRepHealth] = useState<RepHealthRow[]>([]);

  const loadAll = useCallback(async () => {
    const startDay = localStartOfDayIso();
    const startMonth = localStartOfMonthIso();
    const staleCut = new Date(Date.now() - 48 * 3600 * 1000).toISOString();

    const [evRes, actRes, clientsRes, prospectsRes, healthRes, vaReportsRes, vaScoresRes, vaAlertsRes] = await Promise.all([
      supabase.from("prospect_email_events").select("id,sent_at,replied_at,created_at").gte("created_at", startDay).limit(2000),
      supabase
        .from("activities")
        .select("id,prospect_id,type,notes,metadata,created_by,created_at")
        .order("created_at", { ascending: false })
        .limit(80),
      supabase.from("clients").select("id,closing_rep_id,mrr_cents,close_date,status").eq("status", "active").limit(500),
      supabase.from("prospects").select("*").limit(800),
      supabase
        .from("profiles")
        .select("id,full_name,email,health_score,role")
        .in("role", ["sales_rep", "closer", "team_lead"])
        .limit(100),
      supabase.from("va_daily_reports").select("emails_sent,replies_received,calls_booked").eq("report_date", startDay.slice(0, 10)),
      supabase.from("va_scores").select("va_id,standing").order("week_start", { ascending: false }).limit(200),
      supabase.from("va_alerts").select("id").eq("acknowledged", false),
    ]);

    const events = evRes.data ?? [];
    const emailsSentToday = events.length;
    const emailRepliesToday = events.filter((e) => e.replied_at && e.replied_at >= startDay).length;

    const acts = (actRes.data ?? []) as CrmActivityRow[];
    const callsBookedToday = acts.filter((a) => {
      if (a.type !== "stage_changed") return false;
      const to = (a.metadata as { to?: string } | null)?.to;
      return to === "call_booked" && a.created_at >= startDay;
    }).length;

    const clients = clientsRes.data ?? [];
    const closesMtd = clients.filter((c) => c.close_date && c.close_date >= startMonth).length;

    const prospects = (prospectsRes.data ?? []) as Prospect[];
    setProspectsCache(prospects);
    const pipelineOpenDollars = sumOpenPipelineValueDollars(prospects);
    const stale48h = prospects.filter((p) => {
      if (p.stage === "lost" || p.stage === "closed_won") return false;
      return p.last_activity_at < staleCut;
    }).length;
    const activeMrrCents = clients.reduce((s, c) => s + (c.mrr_cents ?? 0), 0);

    /* VA ops aggregates */
    const vaReports = vaReportsRes.data ?? [];
    const vaEmailsSentToday = vaReports.reduce((s: number, r: { emails_sent?: number }) => s + (r.emails_sent ?? 0), 0);
    const vaRepliesTotal = vaReports.reduce((s: number, r: { replies_received?: number }) => s + (r.replies_received ?? 0), 0);
    const vaCallsBookedToday = vaReports.reduce((s: number, r: { calls_booked?: number }) => s + (r.calls_booked ?? 0), 0);
    const vaReplyRate = vaEmailsSentToday > 0 ? (vaRepliesTotal / vaEmailsSentToday) * 100 : 0;

    const vaScoreRows = vaScoresRes.data ?? [];
    const latestByVa = new Map<string, string>();
    for (const row of vaScoreRows as { va_id: string; standing: string }[]) {
      if (!latestByVa.has(row.va_id)) latestByVa.set(row.va_id, row.standing);
    }
    const vaStandings: VaStandingSummary = { green: 0, yellow: 0, red: 0 };
    for (const st of latestByVa.values()) {
      if (st === "green") vaStandings.green++;
      else if (st === "yellow") vaStandings.yellow++;
      else if (st === "red") vaStandings.red++;
    }
    const vaActiveAlerts = (vaAlertsRes.data ?? []).length;

    setKpis({
      emailsSentToday,
      emailRepliesToday,
      callsBookedToday,
      closesMtd,
      pipelineOpenDollars,
      stale48h,
      activeMrrCents,
      vaCallsBookedToday,
      vaEmailsSentToday,
      vaReplyRate,
      vaStandings,
      vaActiveAlerts,
    });
    setActivities(acts);

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
      return;
    }
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
        .sort((a, b) => b.mrrCents - a.mrrCents),
    );

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
        }),
    );
  }, [supabase]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    const ch = supabase
      .channel("ceo-live")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "activities" },
        () => {
          void loadAll();
        },
      )
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
      const p = prospectsCache.find((x) => x.id === pid);
      return p ? p.company_name || p.domain : pid.slice(0, 8);
    },
    [prospectsCache],
  );

  if (!kpis) {
    return (
      <div className="flex min-h-[120px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
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
              <Link href="/crm/va/roster" className="text-emerald-600 hover:underline">
                VA Team
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

      {/* VA Operations section */}
      <div className="rounded-xl border border-indigo-200/80 bg-indigo-50/60 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-indigo-900">VA Operations</h2>
          <Link href="/crm/va/roster" className="text-xs text-indigo-600 hover:underline">
            View VA roster →
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <KpiCard
            label="Calls booked today"
            value={`${kpis.vaCallsBookedToday} / 24`}
            hint={kpis.vaCallsBookedToday < 24 ? "Below target" : "On track"}
          />
          <KpiCard
            label="Emails sent today"
            value={`${kpis.vaEmailsSentToday.toLocaleString()} / 2,700`}
            hint={kpis.vaEmailsSentToday < 2700 ? "Below target" : "On track"}
          />
          <KpiCard
            label="Reply rate"
            value={`${kpis.vaReplyRate.toFixed(1)}%`}
            hint={`Target: 3.4%${kpis.vaReplyRate < 3.4 ? " — below" : ""}`}
          />
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-600">VA standings</div>
            <div className="mt-1 flex gap-3 text-lg font-semibold">
              <span className="text-emerald-600">{kpis.vaStandings.green}G</span>
              <span className="text-amber-500">{kpis.vaStandings.yellow}Y</span>
              <span className="text-rose-600">{kpis.vaStandings.red}R</span>
            </div>
          </div>
          <KpiCard
            label="Active alerts"
            value={kpis.vaActiveAlerts}
            hint={kpis.vaActiveAlerts > 0 ? "Needs attention" : "All clear"}
          />
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
