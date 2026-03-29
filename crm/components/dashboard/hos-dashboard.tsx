"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Users, Target, Filter, Activity as ActivityIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, formatRelativeTime, cn, withTimeout } from "@/lib/utils";
import { buildFunnelRowsFromProspects } from "@/lib/pipeline-funnel";
import { ESTIMATED_PIPELINE_VALUE_PER_PROSPECT } from "@/lib/pipeline-constants";
import { activityToFeedItem, type FeedItem } from "@/lib/activity-feed";
import { getSupabaseClient } from "@/lib/supabase";
import type { Activity, PipelineStage } from "@/types/crm";

interface RepRow {
  id: string;
  name: string;
  closes: number;
  target: number;
  commission: number;
  atRisk: boolean;
}

export function HOSDashboard() {
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({ teamCloses: 0, totalPipeline: 0, mrrAdded: 0 });
  const [reps, setReps] = useState<RepRow[]>([]);
  const [funnelRows, setFunnelRows] = useState<
    { stage: string; count: number; key: PipelineStage }[]
  >([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [teamTarget] = useState(25);

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const supabase = getSupabaseClient();
      const now = new Date();
      const monthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
      const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();

      const [usersRes, commissionsRes, clientsRes, prospectsRes, activitiesRes] = await withTimeout(
        Promise.all([
          supabase.from("users").select("id, name, status, last_close_at").in("role", ["rep", "team_lead"]),
          supabase.from("commissions").select("rep_id, type, amount").eq("month_year", monthYear),
          supabase.from("clients").select("mrr, close_date").eq("status", "active"),
          supabase.from("prospects").select("stage"),
          supabase
            .from("activities")
            .select("id, type, notes, metadata, created_at, created_by")
            .order("created_at", { ascending: false })
            .limit(8),
        ]),
        25_000,
        "HoS dashboard"
      );

      const allReps = usersRes.data ?? [];
      const commissions = commissionsRes.data ?? [];
      const activeClients = clientsRes.data ?? [];
      const prospectStages = (prospectsRes.data ?? []) as { stage: PipelineStage }[];

      const funnel = buildFunnelRowsFromProspects(prospectStages);
      setFunnelRows(funnel);
      const openDealCount = funnel.reduce((s, r) => s + r.count, 0);

      const teamCloses = commissions.filter((c) => c.type === "closing").length;
      const mrrAdded = activeClients
        .filter((c) => c.close_date && c.close_date >= startOfMonth)
        .reduce((s, c) => s + (c.mrr || 0), 0);
      const totalPipeline = openDealCount * ESTIMATED_PIPELINE_VALUE_PER_PROSPECT;

      setStats({ teamCloses, totalPipeline, mrrAdded });

      const repRows: RepRow[] = allReps.map((rep) => {
        const repCommissions = commissions.filter((c) => c.rep_id === rep.id);
        const closes = repCommissions.filter((c) => c.type === "closing").length;
        const totalCommission = repCommissions.reduce((s, c) => s + (c.amount || 0), 0);
        const lastClose = rep.last_close_at ? new Date(rep.last_close_at) : null;
        const daysSinceClose = lastClose ? Math.floor((Date.now() - lastClose.getTime()) / 86400000) : 999;

        return {
          id: rep.id,
          name: rep.name,
          closes,
          target: 5,
          commission: totalCommission,
          atRisk: rep.status === "at_risk" || daysSinceClose >= 14,
        };
      });

      repRows.sort((a, b) => b.closes - a.closes || b.commission - a.commission);
      setReps(repRows);

      const activities = (activitiesRes.data ?? []) as Activity[];
      setFeed(activities.map(activityToFeedItem));
    } catch {
      // fail silently — show empty state
    } finally {
      setLoading(false);
    }
  };

  const mergeFeedItem = useCallback((a: Activity) => {
    setFeed((prev) => {
      const item = activityToFeedItem(a);
      if (prev.some((p) => p.id === item.id)) return prev;
      return [item, ...prev].slice(0, 8);
    });
  }, []);

  useEffect(() => {
    const supabase = getSupabaseClient();
    const channel = supabase.channel(`hos-activity-${Math.random().toString(36).slice(2)}`);
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

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  const totalCloses = reps.reduce((s, r) => s + r.closes, 0);
  const teamProgress = Math.min(100, (totalCloses / teamTarget) * 100);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">Sales Dashboard</h1>
        <p className="text-sm text-text-secondary mt-0.5">Team performance overview.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Team Closes" value={String(totalCloses)} subValue="This month" accent />
        <StatCard label="Pipeline (est.)" value={formatCurrency(stats.totalPipeline)} subValue="Open deals" />
        <StatCard
          label="Avg Close Rate"
          value={reps.length > 0 ? `${Math.round((totalCloses / Math.max(1, reps.length * 5)) * 100)}%` : "0%"}
        />
        <StatCard label="MRR Added" value={formatCurrency(stats.mrrAdded)} />
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
            <p className="text-sm text-text-dim text-center py-8">No open pipeline stages yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart layout="vertical" data={funnelRows} margin={{ left: 4, right: 16, top: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: "#5C5876", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
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
                <Bar dataKey="count" fill="#7B5CF5" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="w-4 h-4 text-accent-light" />
              Rep Leaderboard
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {reps.length === 0 ? (
              <p className="text-xs text-text-dim text-center py-6">No reps yet — invite your team in Settings</p>
            ) : (
              reps.map((rep, i) => (
                <div key={rep.id} className="flex items-center gap-3">
                  <span
                    className={cn("text-sm font-bold w-5 text-center", i === 0 ? "text-yellow" : "text-text-dim")}
                  >
                    #{i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-text-primary">{rep.name}</span>
                      {rep.atRisk && (
                        <Badge variant="warning" className="text-2xs">
                          At Risk
                        </Badge>
                      )}
                    </div>
                    <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          rep.closes >= rep.target ? "bg-green" : "bg-accent"
                        )}
                        style={{ width: `${Math.min(100, (rep.closes / rep.target) * 100)}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-semibold text-text-primary">
                      {rep.closes}/{rep.target}
                    </p>
                    <p className="text-2xs text-text-dim">{formatCurrency(rep.commission)}</p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="w-4 h-4 text-green" />
                Team Target Progress
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center mb-6">
                <div className="text-5xl font-bold text-text-primary mb-1">{totalCloses}</div>
                <div className="text-sm text-text-secondary">of {teamTarget} team target</div>
              </div>
              <div className="h-4 bg-surface-3 rounded-full overflow-hidden mb-3">
                <div
                  className="h-full bg-gradient-to-r from-accent to-accent-light rounded-full transition-all"
                  style={{ width: `${teamProgress}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-text-dim">
                <span>{Math.round(teamProgress)}% achieved</span>
                <span>{Math.max(0, teamTarget - totalCloses)} closes remaining</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ActivityIcon className="w-4 h-4 text-blue" />
                Live activity
                <span className="ml-auto flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-green realtime-dot" />
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {feed.length === 0 ? (
                <p className="text-xs text-text-dim text-center py-4">No recent activity</p>
              ) : (
                feed.map((item) => (
                  <div key={item.id} className="flex items-start gap-3 p-2.5 rounded-lg bg-surface-2">
                    <div
                      className={cn(
                        "w-2 h-2 rounded-full mt-1.5 flex-shrink-0",
                        item.type === "close_won"
                          ? "bg-green"
                          : item.type === "hot_flagged"
                            ? "bg-orange"
                            : item.type === "stage_changed"
                              ? "bg-accent"
                              : "bg-blue"
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-text-primary leading-relaxed">{item.text}</p>
                      <p className="text-2xs text-text-dim mt-0.5">{formatRelativeTime(item.time)}</p>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
