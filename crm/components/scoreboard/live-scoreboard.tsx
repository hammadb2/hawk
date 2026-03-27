"use client";

import { useState, useEffect, useRef } from "react";
import { Trophy, Crown, TrendingUp, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, formatRelativeTime, getInitials, cn } from "@/lib/utils";
import { getSupabaseClient } from "@/lib/supabase";
import { useCRMStore } from "@/store/crm-store";
import { canManageTeam } from "@/lib/auth";

type TimePeriod = "this_month" | "last_month" | "this_quarter";

interface RepScore {
  id: string;
  name: string;
  closes: number;
  target: number;
  commission: number;
  atRisk14Day: boolean;
  rank: number;
}

interface FeedItem {
  id: string;
  text: string;
  amount: number;
  time: string;
}

function getMonthYear(offset = 0): string {
  const d = new Date();
  d.setMonth(d.getMonth() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function getQuarterMonths(): string[] {
  const now = new Date();
  const q = Math.floor(now.getMonth() / 3);
  return [0, 1, 2].map((i) => {
    const d = new Date(now.getFullYear(), q * 3 + i, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
}

export function LiveScoreboard() {
  const { user } = useCRMStore();
  const [period, setPeriod] = useState<TimePeriod>("this_month");
  const [scores, setScores] = useState<RepScore[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [teamTarget] = useState(25);
  const [loading, setLoading] = useState(false);
  const initialLoadDone = useRef(false);
  const channelId = useRef(`scoreboard-${Math.random().toString(36).slice(2)}`);
  const supabaseRef = useRef(getSupabaseClient());

  useEffect(() => {
    initialLoadDone.current = false;
    loadScores();

    const sub = supabaseRef.current
      .channel(channelId.current)
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "commissions" }, () => {
        loadScores(true);
      })
      .subscribe();

    return () => { sub.unsubscribe(); };
  }, [period]);

  const loadScores = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const supabase = supabaseRef.current;

      const monthYears =
        period === "this_month" ? [getMonthYear(0)] :
        period === "last_month" ? [getMonthYear(-1)] :
        getQuarterMonths();

      const [repsRes, commissionsRes, activitiesRes] = await Promise.all([
        supabase.from("users").select("id, name, role, status, last_close_at").in("role", ["rep", "team_lead"]),
        supabase.from("commissions").select("id, rep_id, type, amount, calculated_at")
          .in("month_year", monthYears).eq("type", "closing"),
        supabase.from("activities")
          .select("id, type, metadata, created_at, created_by, prospect_id")
          .eq("type", "close_won")
          .order("created_at", { ascending: false })
          .limit(10),
      ]);

      const reps = repsRes.data ?? [];
      const commissions = commissionsRes.data ?? [];

      const repScores: RepScore[] = reps.map((rep) => {
        const repComms = commissions.filter((c) => c.rep_id === rep.id);
        const closes = repComms.length;
        const commission = repComms.reduce((s, c) => s + (c.amount || 0), 0);
        const lastClose = rep.last_close_at ? new Date(rep.last_close_at) : null;
        const daysSince = lastClose ? Math.floor((Date.now() - lastClose.getTime()) / 86400000) : 999;

        return {
          id: rep.id,
          name: rep.name,
          closes,
          target: 5,
          commission,
          atRisk14Day: rep.status === "at_risk" || daysSince >= 14,
          rank: 0,
        };
      });

      repScores.sort((a, b) => b.closes - a.closes || b.commission - a.commission);
      repScores.forEach((r, i) => { r.rank = i + 1; });
      setScores(repScores);

      // Build feed from activities — look up rep name from reps list
      const activities = activitiesRes.data ?? [];
      const feedItems: FeedItem[] = activities.map((a: any) => {
        const rep = reps.find((r) => r.id === a.created_by);
        return {
          id: a.id,
          text: `${rep?.name ?? "A rep"} closed a deal`,
          amount: a.metadata?.mrr || 0,
          time: a.created_at,
        };
      });
      setFeed(feedItems);
    } catch {
      // fail silently — show empty state
    } finally {
      initialLoadDone.current = true;
      if (!silent) setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  const totalCloses = scores.reduce((s, r) => s + r.closes, 0);
  const teamProgress = (totalCloses / teamTarget) * 100;
  const atTarget = teamProgress >= 100;
  const myScore = user ? scores.find((s) => s.id === user.id) : null;

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary flex items-center gap-2">
            <Trophy className="w-5 h-5 text-yellow" />
            Scoreboard
            <span className="flex items-center gap-1.5 ml-2">
              <span className="w-2 h-2 rounded-full bg-green realtime-dot" />
              <span className="text-xs text-green font-medium">Live</span>
            </span>
          </h1>
          <p className="text-sm text-text-secondary mt-0.5">Team performance rankings</p>
        </div>
        <div className="flex items-center gap-1 bg-surface-2 border border-border rounded-lg p-1">
          {(["this_month", "last_month", "this_quarter"] as TimePeriod[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                period === p ? "bg-surface-3 text-text-primary" : "text-text-dim hover:text-text-secondary"
              )}
            >
              {p === "this_month" ? "This Month" : p === "last_month" ? "Last Month" : "This Quarter"}
            </button>
          ))}
        </div>
      </div>

      <div className={cn("rounded-xl border p-4", atTarget ? "border-yellow/30 bg-yellow/5" : "border-border bg-surface-1")}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {atTarget && <Crown className="w-4 h-4 text-yellow" />}
            <span className="text-sm font-semibold text-text-primary">
              Team Target — {totalCloses} / {teamTarget} closes
            </span>
          </div>
          <span className={cn("text-sm font-bold", atTarget ? "text-yellow" : "text-text-primary")}>
            {Math.round(teamProgress)}%
          </span>
        </div>
        <div className="h-3 bg-surface-3 rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-1000", atTarget ? "bg-gradient-to-r from-yellow to-orange" : "bg-gradient-to-r from-accent to-accent-light")}
            style={{ width: `${Math.min(100, teamProgress)}%` }}
          />
        </div>
        {!atTarget && (
          <p className="text-xs text-text-dim mt-1">{teamTarget - totalCloses} closes to team target</p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {scores.length === 0 ? (
            <p className="text-xs text-text-dim text-center py-12">No reps yet — invite your team in Settings</p>
          ) : (
            <div className="space-y-2">
              {scores.map((rep) => {
                const isMe = myScore?.id === rep.id;
                const progress = Math.min(100, (rep.closes / rep.target) * 100);
                return (
                  <div key={rep.id} className={cn("flex items-center gap-3 p-3.5 rounded-xl border transition-all", isMe ? "border-accent/40 bg-accent/5" : "border-border bg-surface-1")}>
                    <div className={cn("w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm",
                      rep.rank === 1 ? "bg-yellow/20 text-yellow" :
                      rep.rank === 2 ? "bg-surface-3 text-text-secondary" :
                      rep.rank === 3 ? "bg-orange/20 text-orange" :
                      "bg-surface-3 text-text-dim"
                    )}>
                      {rep.rank === 1 ? <Crown className="w-3.5 h-3.5" /> : `#${rep.rank}`}
                    </div>
                    <Avatar className="w-8 h-8 flex-shrink-0">
                      <AvatarFallback className="text-xs">{getInitials(rep.name)}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={cn("text-sm font-medium", isMe ? "text-accent-light" : "text-text-primary")}>
                          {rep.name}{isMe && <span className="text-text-dim font-normal"> (you)</span>}
                        </span>
                        {user && canManageTeam(user) && rep.atRisk14Day && (
                          <Badge variant="warning" className="text-2xs">
                            <AlertTriangle className="w-2.5 h-2.5" /> 14-day
                          </Badge>
                        )}
                      </div>
                      <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                        <div className={cn("h-full rounded-full transition-all", progress >= 100 ? "bg-green" : "bg-accent")} style={{ width: `${progress}%` }} />
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-bold text-text-primary">{rep.closes}/{rep.target}</p>
                      {(user && (canManageTeam(user) || isMe)) && (
                        <p className="text-2xs text-text-dim">{formatCurrency(rep.commission)}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {myScore && (
            <div className="mt-3 p-3 rounded-xl border border-accent/20 bg-accent/5 text-center">
              <p className="text-xs text-text-secondary">
                You are <span className="font-bold text-accent-light">#{myScore.rank}</span> —{" "}
                {myScore.target - myScore.closes > 0 ? (
                  <>{myScore.target - myScore.closes} closes to hit your target</>
                ) : <>You hit your target! 🎉</>}
              </p>
            </div>
          )}
        </div>

        <div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <TrendingUp className="w-4 h-4 text-green" />
                Recent Closes
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {feed.length === 0 ? (
                <p className="text-xs text-text-dim text-center py-4">No closes yet this period</p>
              ) : (
                feed.map((item) => (
                  <div key={item.id} className="flex items-start gap-2 py-2 border-b border-border last:border-0">
                    <TrendingUp className="w-3.5 h-3.5 text-green mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-text-secondary leading-relaxed">{item.text}</p>
                      {item.amount > 0 && <p className="text-2xs text-green font-medium">{formatCurrency(item.amount)}/mo</p>}
                      <p className="text-2xs text-text-dim">{formatRelativeTime(item.time)}</p>
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
