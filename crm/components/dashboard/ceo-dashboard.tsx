"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { AlertTriangle, Bot, TrendingUp, Activity as ActivityIcon, Filter } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, formatRelativeTime, cn, withTimeout } from "@/lib/utils";
import { buildFunnelRowsFromProspects } from "@/lib/pipeline-funnel";
import { getSupabaseClient } from "@/lib/supabase";
import { charlotteApi } from "@/lib/api";
import { activityToFeedItem, type FeedItem } from "@/lib/activity-feed";
import { toast } from "@/components/ui/toast";
import type { Activity, ChurnRisk, ClientStatus, PipelineStage } from "@/types/crm";

interface MRRPoint { month: string; gross: number; net: number }
interface ChurnClient { id: string; company: string; mrr: number; nps: number | null; rep: string; risk: string }
interface CharStats { emails_today?: number; open_rate?: number; reply_rate?: number; hot_leads?: number; closes_attributed?: number }

interface ClientRow {
  id: string;
  mrr: number | null;
  status: ClientStatus;
  churn_risk_score: ChurnRisk;
  close_date: string | null;
  nps_latest: number | null;
  closing_rep_id: string | null;
  prospect: { company_name: string } | null;
  closing_rep: { name: string } | null;
}

export function CEODashboard() {
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<"3M" | "6M" | "12M" | "All">("6M");
  const [mrrHistory, setMrrHistory] = useState<MRRPoint[]>([]);
  const [stats, setStats] = useState({ currentMRR: 0, mrrAdded: 0, mrrAtRisk: 0, activeClients: 0 });
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [churnAlerts, setChurnAlerts] = useState<ChurnClient[]>([]);
  const [charlotteStats, setCharlotteStats] = useState<CharStats>({});
  const [funnelRows, setFunnelRows] = useState<
    { stage: string; count: number; key: PipelineStage }[]
  >([]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const supabase = getSupabaseClient();

        const now = new Date();
        const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();

        const [clientsRes, activitiesRes, prospectsRes] = await withTimeout(
          Promise.all([
            supabase
              .from("clients")
              .select(
                "id, mrr, status, churn_risk_score, close_date, nps_latest, closing_rep_id, prospect:prospect_id(company_name), closing_rep:closing_rep_id(name)"
              ),
            supabase
              .from("activities")
              .select("id, type, notes, metadata, created_at, created_by")
              .order("created_at", { ascending: false })
              .limit(8),
            supabase.from("prospects").select("stage"),
          ]),
          25_000,
          "CEO dashboard"
        );

        if (clientsRes.error) {
          throw new Error(clientsRes.error.message);
        }
        if (activitiesRes.error) {
          throw new Error(activitiesRes.error.message);
        }

        if (cancelled) return;

        const prospectStages = (prospectsRes.error ? [] : prospectsRes.data ?? []) as {
          stage: PipelineStage;
        }[];
        setFunnelRows(buildFunnelRowsFromProspects(prospectStages));

      const clients = (clientsRes.data ?? []) as unknown as ClientRow[];
      const activeClients = clients.filter((c) => c.status === "active");

      // MRR stats
      const currentMRR = activeClients.reduce((s, c) => s + (c.mrr || 0), 0);
      const mrrAdded = clients
        .filter((c) => c.close_date && c.close_date >= startOfMonth && c.status !== "churned")
        .reduce((s, c) => s + (c.mrr || 0), 0);
      const mrrAtRisk = clients
        .filter((c) => ["high", "critical"].includes(c.churn_risk_score) && c.status === "active")
        .reduce((s, c) => s + (c.mrr || 0), 0);

      setStats({ currentMRR, mrrAdded, mrrAtRisk, activeClients: activeClients.length });

      // Build MRR history from client close dates (cumulative)
      const monthlyMRR: Record<string, number> = {};
      clients
        .filter((c) => c.close_date && c.status !== "churned")
        .forEach((c) => {
          const d = new Date(c.close_date as string);
          const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
          monthlyMRR[key] = (monthlyMRR[key] || 0) + (c.mrr || 0);
        });

      const sortedMonths = Object.keys(monthlyMRR).sort();
      let cumulative = 0;
      const history: MRRPoint[] = sortedMonths.map((key) => {
        cumulative += monthlyMRR[key];
        const [, m] = key.split("-");
        const label = new Date(0, Number(m) - 1).toLocaleString("default", { month: "short" });
        return { month: label, gross: cumulative, net: Math.round(cumulative * 0.93) };
      });
      setMrrHistory(history);

      // Activity feed — no nested joins, just raw fields
      const activities = (activitiesRes.data ?? []) as Activity[];
      const feedItems: FeedItem[] = activities.map(activityToFeedItem);
      setFeed(feedItems);

      // Churn alerts
      const churn = clients
        .filter((c) => ["high", "critical"].includes(c.churn_risk_score) && c.status === "active")
        .sort((a, b) => (b.mrr || 0) - (a.mrr || 0))
        .slice(0, 5)
        .map((c) => ({
          id: c.id,
          company: c.prospect?.company_name ?? `Client ${c.id.slice(0, 6)}`,
          mrr: c.mrr || 0,
          nps: c.nps_latest,
          rep: c.closing_rep?.name ?? "—",
          risk: c.churn_risk_score,
        }));
      setChurnAlerts(churn);

      // Charlotte stats — fetch separately so it never blocks the main load
      charlotteApi.stats().then((charRes) => {
        if (cancelled) return;
        if (charRes.success && charRes.data) {
          setCharlotteStats(charRes.data as CharStats);
        }
      }).catch(() => {});
    } catch (e) {
      if (!cancelled) {
        toast({
          title: "Could not load dashboard",
          description: e instanceof Error ? e.message : "Check Supabase env vars and network.",
          variant: "destructive",
        });
      }
    } finally {
      if (!cancelled) setLoading(false);
    }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const mergeFeedItem = useCallback((a: Activity) => {
    setFeed((prev) => {
      const item = activityToFeedItem(a);
      if (prev.some((p) => p.id === item.id)) return prev;
      return [item, ...prev].slice(0, 8);
    });
  }, []);

  useEffect(() => {
    const supabase = getSupabaseClient();
    const channel = supabase.channel(`ceo-activity-${Math.random().toString(36).slice(2)}`);
    channel.on(
      "postgres_changes",
      { event: "INSERT", schema: "public", table: "activities" },
      (payload) => {
        const row = payload.new as Activity;
        if (row?.id && row.type) {
          mergeFeedItem(row);
        }
      }
    );
    channel.subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [mergeFeedItem]);

  const filteredHistory = (() => {
    const n = timeRange === "3M" ? 3 : timeRange === "6M" ? 6 : timeRange === "12M" ? 12 : undefined;
    return n ? mrrHistory.slice(-n) : mrrHistory;
  })();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">CEO Dashboard</h1>
        <p className="text-sm text-text-secondary mt-0.5">Full organization overview.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard label="Current MRR" value={formatCurrency(stats.currentMRR)} accent />
        <StatCard label="Net MRR" value={formatCurrency(Math.round(stats.currentMRR * 0.93))} />
        <StatCard label="MRR Added" value={formatCurrency(stats.mrrAdded)} subValue="This month" />
        <StatCard label="MRR at Risk" value={formatCurrency(stats.mrrAtRisk)} subValue="High churn" />
        <StatCard label="Active Clients" value={String(stats.activeClients)} />
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-accent-light" />
            Pipeline funnel
          </CardTitle>
          <Button variant="secondary" size="sm" asChild>
            <Link href="/pipeline">Open pipeline</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {funnelRows.every((r) => r.count === 0) ? (
            <p className="text-sm text-text-dim text-center py-8">No open pipeline stages yet — add prospects to see volume by stage.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart layout="vertical" data={funnelRows} margin={{ left: 4, right: 16, top: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="stage"
                  width={100}
                  tick={{ fill: "#9B98B4", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }}
                  formatter={(v: number) => [String(v), "Prospects"]}
                />
                <Bar dataKey="count" fill="#7B5CF5" radius={[0, 6, 6, 0]} name="Open deals" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-accent-light" />
                Revenue Trend
              </CardTitle>
              <div className="flex items-center gap-1">
                {(["3M", "6M", "12M", "All"] as const).map((range) => (
                  <button
                    key={range}
                    onClick={() => setTimeRange(range)}
                    className={cn(
                      "px-2 py-0.5 rounded text-xs font-medium transition-colors",
                      timeRange === range ? "bg-accent text-white" : "text-text-dim hover:text-text-secondary"
                    )}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {filteredHistory.length === 0 ? (
              <div className="flex items-center justify-center h-[220px] text-text-dim text-sm">
                No revenue data yet — closes will appear here
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={filteredHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" />
                  <XAxis dataKey="month" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip
                    contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }}
                    labelStyle={{ color: "#9B98B4" }}
                    formatter={(v: number) => [formatCurrency(v), ""]}
                  />
                  <Legend iconType="circle" />
                  <Line type="monotone" dataKey="gross" stroke="#7B5CF5" strokeWidth={2} dot={false} name="Gross MRR" />
                  <Line type="monotone" dataKey="net" stroke="#34D399" strokeWidth={2} dot={false} name="Net MRR" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-accent-light" />
              Charlotte
              <span className="ml-auto flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green realtime-dot" />
                <span className="text-xs text-green font-medium">Live</span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { label: "Emails Today", value: charlotteStats.emails_today != null ? String(charlotteStats.emails_today) : "—" },
              { label: "Open Rate", value: charlotteStats.open_rate != null ? `${charlotteStats.open_rate}%` : "—" },
              { label: "Reply Rate", value: charlotteStats.reply_rate != null ? `${charlotteStats.reply_rate}%` : "—" },
              { label: "Hot Leads", value: charlotteStats.hot_leads != null ? String(charlotteStats.hot_leads) : "—" },
              { label: "Closes Attributed", value: charlotteStats.closes_attributed != null ? String(charlotteStats.closes_attributed) : "—" },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">{label}</span>
                <span className="text-sm font-semibold text-text-primary">{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ActivityIcon className="w-4 h-4 text-blue" />
              Live Activity Feed
              <span className="ml-auto flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green realtime-dot" />
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {feed.length === 0 ? (
              <p className="text-xs text-text-dim text-center py-6">No activity yet — activity will appear here as your team works</p>
            ) : (
              feed.map((item) => (
                <div key={item.id} className="flex items-start gap-3 p-2.5 rounded-lg bg-surface-2">
                  <div className={cn(
                    "w-2 h-2 rounded-full mt-1.5 flex-shrink-0",
                    item.type === "close_won" ? "bg-green" :
                    item.type === "hot_flagged" ? "bg-orange" :
                    item.type === "stage_changed" ? "bg-accent" : "bg-blue"
                  )} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-text-primary leading-relaxed">{item.text}</p>
                    <p className="text-2xs text-text-dim mt-0.5">{formatRelativeTime(item.time)}</p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red" />
              Churn Alerts
              {churnAlerts.length > 0 && (
                <Badge variant="destructive" className="ml-auto">{churnAlerts.length} at risk</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {churnAlerts.length === 0 ? (
              <p className="text-xs text-text-dim text-center py-6">No high churn risk clients</p>
            ) : (
              churnAlerts.map((client) => (
                <div key={client.id} className="flex items-center gap-3 p-3 rounded-lg border border-red/20 bg-red/5">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary">{client.company}</p>
                    <p className="text-xs text-text-dim">
                      Rep: {client.rep}{client.nps != null ? ` · NPS: ${client.nps}` : ""}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-semibold text-text-primary">{formatCurrency(client.mrr)}/mo</p>
                    <Badge variant="destructive" className="text-2xs capitalize">{client.risk} Risk</Badge>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
