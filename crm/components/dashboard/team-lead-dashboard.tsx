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
import { Users, Filter, Activity as ActivityIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, formatRelativeTime, cn, withTimeout } from "@/lib/utils";
import { buildFunnelRowsFromProspects } from "@/lib/pipeline-funnel";
import { ESTIMATED_PIPELINE_VALUE_PER_PROSPECT } from "@/lib/pipeline-constants";
import { activityToFeedItem, type FeedItem } from "@/lib/activity-feed";
import { useCRMStore } from "@/store/crm-store";
import { getSupabaseClient } from "@/lib/supabase";
import type { Activity, PipelineStage } from "@/types/crm";

interface RepRow {
  id: string;
  name: string;
  status: string;
  last_close_at: string | null;
  closes: number;
  target: number;
}

export function TeamLeadDashboard() {
  const { user } = useCRMStore();
  const [loading, setLoading] = useState(false);
  const [teamReps, setTeamReps] = useState<RepRow[]>([]);
  const [stats, setStats] = useState({
    teamCloses: 0,
    ownCloses: 0,
    overrideEarned: 0,
    openDeals: 0,
    pipelineValue: 0,
  });
  const [funnelRows, setFunnelRows] = useState<
    { stage: string; count: number; key: PipelineStage }[]
  >([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const supabase = getSupabaseClient();

      const { data: { user: authUser } } = await supabase.auth.getUser();
      if (!authUser) return;

      const now = new Date();
      const monthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

      const [repsRes, commissionsRes, stagesRes, activitiesRes] = await withTimeout(
        Promise.all([
          supabase.from("users").select("id, name, status, last_close_at").eq("team_lead_id", authUser.id).in("role", ["rep"]),
          supabase.from("commissions").select("rep_id, type, amount, month_year").eq("month_year", monthYear),
          supabase.from("prospects").select("stage"),
          supabase
            .from("activities")
            .select("id, type, notes, metadata, created_at, created_by")
            .order("created_at", { ascending: false })
            .limit(8),
        ]),
        25_000,
        "Team lead dashboard"
      );

      const reps = repsRes.data ?? [];
      const commissions = commissionsRes.data ?? [];
      const stageRows = (stagesRes.data ?? []) as { stage: PipelineStage }[];

      const funnel = buildFunnelRowsFromProspects(stageRows);
      setFunnelRows(funnel);
      const openDeals = funnel.reduce((s, r) => s + r.count, 0);
      const pipelineValue = openDeals * ESTIMATED_PIPELINE_VALUE_PER_PROSPECT;

      const repIds = reps.map((r) => r.id);

      const teamCommissions = commissions.filter((c) => repIds.includes(c.rep_id) && c.type === "closing");
      const teamCloses = teamCommissions.length;

      const ownCommissions = commissions.filter((c) => c.rep_id === authUser.id && c.type === "closing");
      const ownCloses = ownCommissions.length;

      const overrideEarned = teamCommissions.reduce((s, c) => s + (c.amount || 0) * 0.05, 0);

      setStats({ teamCloses, ownCloses, overrideEarned, openDeals, pipelineValue });

      const closesByRep: Record<string, number> = {};
      teamCommissions.forEach((c) => {
        closesByRep[c.rep_id] = (closesByRep[c.rep_id] || 0) + 1;
      });

      const repRows: RepRow[] = reps.map((r) => {
        const lastClose = r.last_close_at ? new Date(r.last_close_at) : null;
        const daysSince = lastClose ? Math.floor((Date.now() - lastClose.getTime()) / 86400000) : 999;
        const atRisk = r.status === "at_risk" || daysSince >= 14;
        return {
          id: r.id,
          name: r.name,
          status: atRisk ? "at_risk" : r.status,
          last_close_at: r.last_close_at,
          closes: closesByRep[r.id] ?? 0,
          target: 5,
        };
      });

      setTeamReps(repRows);

      const activities = (activitiesRes.data ?? []) as Activity[];
      setFeed(activities.map(activityToFeedItem));
    } catch {
      // fail silently
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
    const channel = supabase.channel(`tl-activity-${Math.random().toString(36).slice(2)}`);
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

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">Team Dashboard</h1>
        <p className="text-sm text-text-secondary mt-0.5">
          Your team&apos;s performance{user?.name ? ` — ${user.name.split(" ")[0]}` : ""}.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Team Closes" value={String(stats.teamCloses)} subValue="This month" accent />
        <StatCard label="Your Closes" value={String(stats.ownCloses)} />
        <StatCard label="Override Earned" value={formatCurrency(stats.overrideEarned)} />
        <StatCard
          label="Pipeline (est.)"
          value={formatCurrency(stats.pipelineValue)}
          subValue={`${stats.openDeals} open deals`}
        />
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-accent-light" />
            Team pipeline funnel
          </CardTitle>
          <Button variant="secondary" size="sm" asChild>
            <Link href="/pipeline">Open pipeline</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {funnelRows.every((r) => r.count === 0) ? (
            <p className="text-sm text-text-dim text-center py-8">
              No open deals in your visible pipeline — assign prospects or add leads.
            </p>
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
              My Team
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {teamReps.length === 0 ? (
              <p className="text-sm text-text-dim text-center py-6">No reps assigned to you yet.</p>
            ) : (
              teamReps.map((rep) => (
                <div
                  key={rep.id}
                  className={cn(
                    "flex items-center gap-3 p-3 rounded-lg border transition-all",
                    rep.status === "at_risk" ? "border-red/30 bg-red/5" : "border-border bg-surface-2"
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-text-primary">{rep.name}</span>
                      {rep.status === "at_risk" && (
                        <Badge variant="destructive" className="text-2xs">
                          14-Day Risk
                        </Badge>
                      )}
                    </div>
                    <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          rep.closes >= rep.target ? "bg-green" : rep.status === "at_risk" ? "bg-red" : "bg-accent"
                        )}
                        style={{ width: `${Math.min((rep.closes / rep.target) * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-semibold text-text-primary">
                      {rep.closes}/{rep.target}
                    </p>
                    <p className="text-2xs text-text-dim">
                      {rep.last_close_at ? `Last: ${formatRelativeTime(rep.last_close_at)}` : "No closes yet"}
                    </p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ActivityIcon className="w-4 h-4 text-blue" />
              Team activity
              <span className="ml-auto flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green realtime-dot" />
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {feed.length === 0 ? (
              <p className="text-xs text-text-dim text-center py-6">No recent activity for your team</p>
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
  );
}
