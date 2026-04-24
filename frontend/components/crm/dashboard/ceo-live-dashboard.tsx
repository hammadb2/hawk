"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  AlertTriangle,
  DollarSign,
  Mail,
  MessageSquareReply,
  Phone,
  TrendingUp,
  Trophy,
} from "lucide-react";
import type { CrmActivityRow, Profile } from "@/lib/crm/types";
import { fetchCrmDashboardKpis } from "@/lib/crm/dashboard-kpis";
import { useClients, useProfiles, useProspects } from "@/lib/crm/hooks";
import { cn } from "@/lib/utils";

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

function formatRelativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  const sec = Math.floor(diff / 1000);
  if (sec < 45) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} minute${min === 1 ? "" : "s"} ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? "" : "s"} ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} day${day === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleDateString();
}

function activityBorderClass(type: string): string {
  if (type === "stage_changed") return "border-l-signal";
  if (type.includes("note")) return "border-l-blue-500";
  if (type.includes("call")) return "border-l-purple-500";
  if (type.includes("email")) return "border-l-amber-500";
  return "border-l-slate-600";
}

function rankTextClass(i: number): string {
  if (i === 0) return "text-yellow-400";
  if (i === 1) return "text-ink-200";
  if (i === 2) return "text-signal-400";
  return "text-signal";
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
  const { data: clients = [] } = useClients();
  const { data: profileRows = [] } = useProfiles();
  const { data: allProspects = [] } = useProspects();
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [activities, setActivities] = useState<CrmActivityRow[]>([]);
  const [activityFilter, setActivityFilter] = useState<string>("all");
  const [prospectLabels, setProspectLabels] = useState<Record<string, string>>({});

  const leaderboard = useMemo(() => {
    const startMonth = localStartOfMonthIso();
    const activeClients = clients.filter((c) => c.status === "active");
    const mtdClients = activeClients.filter((c) => c.close_date && c.close_date >= startMonth && c.closing_rep_id);
    const byRep = new Map<string, { closes: number; mrrCents: number }>();
    for (const c of mtdClients) {
      const rid = c.closing_rep_id as string;
      const cur = byRep.get(rid) ?? { closes: 0, mrrCents: 0 };
      cur.closes += 1;
      cur.mrrCents += c.mrr_cents ?? 0;
      byRep.set(rid, cur);
    }
    const repIds = Array.from(byRep.keys());
    if (repIds.length === 0) return [];
    const nameById = new Map(profileRows.map((p) => [p.id, p.full_name || p.email || p.id]));
    return repIds
      .map((id) => ({
        repId: id,
        name: nameById.get(id) ?? id,
        closes: byRep.get(id)?.closes ?? 0,
        mrrCents: byRep.get(id)?.mrrCents ?? 0,
      }))
      .sort((a, b) => b.mrrCents - a.mrrCents);
  }, [clients, profileRows]);

  const callsBooked = useMemo(() => {
    return allProspects
      .filter((p) => p.stage === "call_booked")
      .slice()
      .sort((a, b) => {
        const ta = a.call_booked_at ? new Date(a.call_booked_at).getTime() : 0;
        const tb = b.call_booked_at ? new Date(b.call_booked_at).getTime() : 0;
        return tb - ta;
      });
  }, [allProspects]);

  const repHealth = useMemo(() => {
    return profileRows
      .filter((r) => r.role === "sales_rep" || r.role === "closer" || r.role === "team_lead")
      .map((r) => ({
        repId: r.id,
        name: r.full_name || r.email || r.id.slice(0, 8),
        healthScore: typeof r.health_score === "number" ? r.health_score : null,
      }))
      .sort((a, b) => {
        const av = a.healthScore ?? -1;
        const bv = b.healthScore ?? -1;
        return av - bv;
      });
  }, [profileRows]);

  const loadFeed = useCallback(async () => {
    const startDay = localStartOfDayIso();
    const startMonth = localStartOfMonthIso();

    const [actRes, kpiPayload] = await Promise.all([
      supabase
        .from("activities")
        .select("id,prospect_id,type,notes,metadata,created_by,created_at")
        .order("created_at", { ascending: false })
        .limit(80),
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
      setKpis({
        emailsSentToday: 0,
        emailRepliesToday: 0,
        callsBookedToday: 0,
        closesMtd: clients.filter((c) => c.close_date && c.close_date >= startMonth).length,
        pipelineOpenDollars: 0,
        stale48h: 0,
        activeMrrCents: clients.filter((c) => c.status === "active").reduce((s, c) => s + (c.mrr_cents ?? 0), 0),
      });
    }

    const prospectIds = Array.from(
      new Set(acts.map((a) => a.prospect_id).filter((x): x is string => typeof x === "string" && !!x))
    );
    if (prospectIds.length) {
      const { data: pl } = await supabase.from("prospects").select("id,company_name,domain").in("id", prospectIds);
      const map: Record<string, string> = {};
      for (const row of pl ?? []) {
        map[row.id] = (row.company_name as string | null) || (row.domain as string) || row.id.slice(0, 8);
      }
      setProspectLabels(map);
    } else {
      setProspectLabels({});
    }
  }, [supabase, accessToken, clients]);

  useEffect(() => {
    void loadFeed();
  }, [loadFeed]);

  useEffect(() => {
    const ch = supabase
      .channel("ceo-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "activities" }, () => {
        void loadFeed();
      })
      .subscribe();
    return () => {
      void supabase.removeChannel(ch);
    };
  }, [supabase, loadFeed]);

  const filteredActivities = useMemo(() => {
    if (activityFilter === "all") return activities;
    if (activityFilter === "note") return activities.filter((a) => a.type.includes("note"));
    if (activityFilter === "call") return activities.filter((a) => a.type.includes("call"));
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
        <div className="h-24 animate-pulse rounded-xl bg-crmSurface" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-crmSurface" />
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-crmSurface" />
          ))}
        </div>
      </div>
    );
  }

  const roleNote = profile.role === "hos" ? "HoS" : "CEO";
  const mrrFormatted = `$${(kpis.activeMrrCents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}/mo`;

  return (
    <div className="space-y-6">
      <div className="w-full rounded-xl border border-crmBorder border-l-[4px] border-l-signal bg-crmSurface p-5 shadow-lg">
        <p className="text-xs font-medium uppercase tracking-wider text-ink-0">Active MRR</p>
        <p className="mt-1 text-4xl font-bold text-white">{mrrFormatted}</p>
        <p className="mt-2 text-xs text-ink-200">
          Live ops ({roleNote}) — KPIs from <code className="text-signal/90">/api/crm/dashboard/kpis</code> (60s cache).
          Activity updates in real time.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard icon={<Mail className="h-5 w-5 text-signal" strokeWidth={2} />} label="Emails sent today" value={kpis.emailsSentToday} />
        <KpiCard
          icon={<MessageSquareReply className="h-5 w-5 text-signal" strokeWidth={2} />}
          label="Replies today"
          value={kpis.emailRepliesToday}
        />
        <KpiCard icon={<Phone className="h-5 w-5 text-signal" strokeWidth={2} />} label="Calls booked today" value={kpis.callsBookedToday} />
        <KpiCard icon={<Trophy className="h-5 w-5 text-signal" strokeWidth={2} />} label="Closes (MTD)" value={kpis.closesMtd} />
      </div>

      <div className="rounded-xl border border-crmBorder bg-crmSurface p-4 shadow-lg">
        <h3 className="text-sm font-medium text-white">Calls booked</h3>
        <p className="text-xs text-ink-0">Prospects in call_booked — next step is show rate.</p>
        <ul className="mt-3 max-h-[280px] space-y-2 overflow-y-auto text-sm">
          {callsBooked.length === 0 && <li className="text-ink-0">No calls booked in pipeline right now.</li>}
          {callsBooked.map((p) => {
            const when = p.call_booked_at
              ? new Date(p.call_booked_at).toLocaleString(undefined, {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })
              : "—";
            const contact = p.contact_name || p.contact_email || "—";
            return (
              <li
                key={p.id}
                className="flex flex-col gap-1 rounded-lg border border-crmBorder bg-[#111118] px-3 py-2 text-ink-100 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <Link href={`/crm/prospects/${p.id}`} className="font-medium text-signal hover:underline">
                    {p.company_name || p.domain || p.id.slice(0, 8)}
                  </Link>
                  <p className="text-xs text-ink-0">
                    {contact} · Hawk {p.hawk_score ?? "—"}
                  </p>
                </div>
                <div className="text-right text-xs text-ink-200">
                  <span className="block text-ink-0">Scheduled</span>
                  {when}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <KpiCard
          icon={<TrendingUp className="h-5 w-5 text-signal" strokeWidth={2} />}
          label="Open pipeline ($ est.)"
          value={`$${kpis.pipelineOpenDollars.toLocaleString()}`}
        />
        <KpiCard
          icon={<AlertTriangle className="h-5 w-5 text-signal" strokeWidth={2} />}
          label="Stale 48h+ (open)"
          value={kpis.stale48h}
          hint="Any open stage, no activity 48h+"
        />
        <KpiCard
          icon={<DollarSign className="h-5 w-5 text-signal" strokeWidth={2} />}
          label="Active client MRR"
          value={`$${(kpis.activeMrrCents / 100).toLocaleString()}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-crmBorder bg-crmSurface p-4 shadow-lg">
          <h3 className="text-sm font-medium text-white">Rep leaderboard (MTD)</h3>
          <p className="text-xs text-ink-0">By revenue closed this month</p>
          <ul className="mt-3 space-y-2 text-sm">
            {leaderboard.length === 0 && <li className="text-ink-0">No closes recorded this month yet.</li>}
            {leaderboard.map((row, i) => (
              <li key={row.repId} className="flex justify-between gap-2 text-ink-100">
                <span>
                  <span className={cn("mr-1.5 font-semibold tabular-nums", rankTextClass(i))}>{i + 1}.</span>
                  {row.name}
                </span>
                <span className="text-ink-200">
                  {row.closes} deal{row.closes === 1 ? "" : "s"} · ${(row.mrrCents / 100).toLocaleString()} MRR
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-crmBorder bg-crmSurface p-4 shadow-lg">
          <h3 className="text-sm font-medium text-white">Rep health (0–100)</h3>
          <p className="text-xs text-ink-0">Daily score from pipeline hygiene; under 50 stands out.</p>
          <ul className="mt-3 max-h-[220px] space-y-2 overflow-y-auto text-sm">
            {repHealth.length === 0 && <li className="text-ink-0">No sales roles loaded.</li>}
            {repHealth.map((row) => (
              <li key={row.repId} className="flex justify-between gap-2 text-ink-100">
                <span>{row.name}</span>
                <span
                  className={
                    row.healthScore !== null && row.healthScore < 50 ? "font-medium text-red" : "text-ink-200"
                  }
                >
                  {row.healthScore ?? "—"}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-crmBorder bg-crmSurface p-4 shadow-lg">
          <h3 className="text-sm font-medium text-white">Quick links</h3>
          <ul className="mt-3 space-y-2 text-sm">
            <li>
              <Link href="/crm/pipeline" className="text-signal hover:underline">
                Pipeline
              </Link>
            </li>
            <li>
              <Link href="/crm/settings" className="text-signal hover:underline">
                Settings &amp; monitor history
              </Link>
            </li>
          </ul>
        </div>
      </div>

      <div className="rounded-xl border border-crmBorder bg-crmSurface p-4 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-white">Activity feed</h3>
          <select
            value={activityFilter}
            onChange={(e) => setActivityFilter(e.target.value)}
            className="rounded-lg border border-crmBorder bg-crmSurface2 px-2 py-1 text-xs text-ink-100"
          >
            <option value="all">All types</option>
            <option value="stage_changed">Stage changes</option>
            <option value="note">Notes</option>
            <option value="call">Calls</option>
          </select>
        </div>
        <ul className="mt-3 max-h-[420px] space-y-2 overflow-y-auto text-sm">
          {filteredActivities.map((a) => (
            <li
              key={a.id}
              className={cn(
                "rounded-lg border border-y border-r border-crmBorder bg-crmSurface2 py-2 pl-3 pr-3 shadow-sm border-l-4",
                activityBorderClass(a.type),
              )}
            >
              <div className="flex flex-wrap justify-between gap-2 text-ink-200">
                <span className="font-medium text-ink-100">{a.type.replace(/_/g, " ")}</span>
                <span className="text-xs text-ink-0">{formatRelativeTime(a.created_at)}</span>
              </div>
              <div className="mt-1 text-ink-100">
                {a.prospect_id ? (
                  <Link href={`/crm/prospects/${a.prospect_id}`} className="hover:text-signal hover:underline">
                    {prospectLabel(a.prospect_id)}
                  </Link>
                ) : (
                  "—"
                )}
              </div>
              {a.type === "stage_changed" && a.metadata && (
                <p className="mt-1 text-xs text-ink-0">
                  {(a.metadata as { from?: string; to?: string }).from} → {(a.metadata as { to?: string }).to}
                </p>
              )}
              {a.notes && <p className="mt-1 text-xs text-ink-200">{a.notes}</p>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function KpiCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-crmBorder bg-[#111118] p-4 shadow-lg">
      <div className="flex items-start justify-between gap-2">
        {icon}
      </div>
      <div className="mt-3 text-3xl font-bold text-white">{value}</div>
      <div className="mt-1 text-xs font-medium uppercase tracking-wider text-ink-0">{label}</div>
      {hint && <p className="mt-2 text-xs text-ink-0">{hint}</p>}
    </div>
  );
}
