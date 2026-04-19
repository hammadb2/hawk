"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { createClient } from "@/lib/supabase/client";

type GuardianEventRow = {
  id: string;
  client_id: string;
  event_type: string;
  severity: string;
  details: Record<string, unknown> | null;
  page_url: string | null;
  created_at: string;
  clients: { company_name: string | null; domain: string | null } | null;
};

type GuardianProfileRow = {
  client_id: string;
  domain: string | null;
  bec_risk_score: number;
  safe_browsing_status: string;
  last_profiled_at: string | null;
};

function dayKey(iso: string) {
  return iso.slice(0, 10);
}

function clientLabel(e: GuardianEventRow) {
  const c = e.clients as { company_name: string | null; domain: string | null } | { company_name: string | null; domain: string | null }[] | null;
  const row = Array.isArray(c) ? c[0] : c;
  return row?.company_name || row?.domain || e.client_id.slice(0, 8);
}

function severityChip(sev: string) {
  const s = (sev || "").toLowerCase();
  const cls =
    s === "critical" || s === "high"
      ? "bg-rose-500/15 text-rose-300 ring-rose-500/40"
      : s === "medium"
        ? "bg-amber-500/15 text-amber-200 ring-amber-500/35"
        : "bg-slate-500/15 text-slate-300 ring-slate-500/30";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${cls}`}>{sev || "—"}</span>
  );
}

export default function CrmGuardianPage() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [events, setEvents] = useState<GuardianEventRow[]>([]);
  const [profiles, setProfiles] = useState<GuardianProfileRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const privileged = profile?.role === "ceo" || profile?.role === "hos";

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (!authReady) return;
      if (!session?.access_token) {
        setErr("Sign in required");
        setLoading(false);
        return;
      }
      if (!privileged) {
        setErr("Guardian is limited to CEO and Head of Security.");
        setLoading(false);
        return;
      }
      setLoading(true);
      setErr(null);
      const [evRes, prRes] = await Promise.all([
        supabase
          .from("guardian_events")
          .select("id, client_id, event_type, severity, details, page_url, created_at, clients(company_name, domain)")
          .order("created_at", { ascending: false })
          .limit(200),
        supabase
          .from("client_guardian_profiles")
          .select("client_id, domain, bec_risk_score, safe_browsing_status, last_profiled_at")
          .order("updated_at", { ascending: false })
          .limit(300),
      ]);
      if (cancelled) return;
      if (evRes.error) {
        setErr(evRes.error.message);
        setEvents([]);
      } else {
        setEvents((evRes.data as unknown as GuardianEventRow[]) || []);
      }
      if (prRes.error) {
        setErr((e) => e || prRes.error!.message);
        setProfiles([]);
      } else {
        setProfiles((prRes.data as unknown as GuardianProfileRow[]) || []);
      }
      setLoading(false);
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [authReady, session?.access_token, supabase, privileged]);

  const lineData = useMemo(() => {
    const counts = new Map<string, number>();
    const today = new Date();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const k = d.toISOString().slice(0, 10);
      counts.set(k, 0);
    }
    for (const e of events) {
      const k = dayKey(e.created_at);
      if (counts.has(k)) counts.set(k, (counts.get(k) || 0) + 1);
    }
    return Array.from(counts.entries()).map(([date, count]) => ({ date, count }));
  }, [events]);

  const barData = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of events) {
      const t = e.event_type || "unknown";
      m.set(t, (m.get(t) || 0) + 1);
    }
    return Array.from(m.entries())
      .map(([type, count]) => ({ type, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  }, [events]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-24 md:pb-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Guardian</h1>
        <p className="mt-1 text-sm text-slate-400">
          Extension-fed signals, client risk profiles, and BEC / lookalike context for executive review.
        </p>
      </div>

      {err && <p className="text-sm text-rose-400">{err}</p>}

      {loading ? (
        <div className="flex justify-center py-16 text-slate-500">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-crmBorder border-t-emerald-500" />
        </div>
      ) : privileged ? (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-crmBorder bg-crmSurface p-4">
              <h2 className="text-sm font-semibold text-slate-200">Events (14 days)</h2>
              <div className="mt-3 h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={lineData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a3340" />
                    <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ background: "#121822", border: "1px solid #2a3340", borderRadius: 8 }}
                      labelStyle={{ color: "#e2e8f0" }}
                    />
                    <Line type="monotone" dataKey="count" stroke="#34d399" strokeWidth={2} dot={false} name="Events" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="rounded-xl border border-crmBorder bg-crmSurface p-4">
              <h2 className="text-sm font-semibold text-slate-200">Top event types</h2>
              <div className="mt-3 h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData} layout="vertical" margin={{ left: 8, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a3340" />
                    <XAxis type="number" allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <YAxis type="category" dataKey="type" width={120} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ background: "#121822", border: "1px solid #2a3340", borderRadius: 8 }}
                      labelStyle={{ color: "#e2e8f0" }}
                    />
                    <Bar dataKey="count" fill="#22d3ee" radius={[0, 4, 4, 0]} name="Count" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-crmBorder bg-crmSurface2 p-4">
            <h2 className="text-sm font-semibold text-slate-200">BEC risk snapshot (profiled clients)</h2>
            <p className="mt-1 text-xs text-slate-500">Higher scores surface urgency keywords and domain heuristics from the server profiler.</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm text-slate-200">
                <thead className="border-b border-crmBorder text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="py-2 pr-3">Domain</th>
                    <th className="py-2 pr-3">BEC score</th>
                    <th className="py-2 pr-3">Safe Browsing</th>
                    <th className="py-2">Last profiled</th>
                  </tr>
                </thead>
                <tbody>
                  {profiles.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-slate-500">
                        No profiles yet — they appear after API profiling or extension activity.
                      </td>
                    </tr>
                  ) : (
                    profiles.slice(0, 25).map((p) => (
                      <tr key={p.client_id} className="border-b border-crmBorder/80">
                        <td className="py-2 pr-3 font-mono text-xs text-slate-300">{p.domain || p.client_id}</td>
                        <td className="py-2 pr-3">{p.bec_risk_score}</td>
                        <td className="py-2 pr-3">{p.safe_browsing_status}</td>
                        <td className="py-2 text-xs text-slate-500">
                          {p.last_profiled_at ? new Date(p.last_profiled_at).toLocaleString() : "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-crmBorder bg-crmSurface p-4">
            <h2 className="text-sm font-semibold text-slate-200">Recent events</h2>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-crmBorder text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="py-2 pr-3">When</th>
                    <th className="py-2 pr-3">Client</th>
                    <th className="py-2 pr-3">Type</th>
                    <th className="py-2 pr-3">Severity</th>
                    <th className="py-2">Page</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-slate-500">
                        No Guardian events logged yet.
                      </td>
                    </tr>
                  ) : (
                    events.map((e) => (
                      <tr key={e.id} className="border-b border-crmBorder/70">
                        <td className="py-2 pr-3 text-xs text-slate-500">{new Date(e.created_at).toLocaleString()}</td>
                        <td className="py-2 pr-3">{clientLabel(e)}</td>
                        <td className="py-2 pr-3 font-mono text-xs">{e.event_type}</td>
                        <td className="py-2 pr-3">{severityChip(e.severity)}</td>
                        <td className="max-w-[240px] truncate py-2 text-xs text-slate-500" title={e.page_url || ""}>
                          {e.page_url || "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
