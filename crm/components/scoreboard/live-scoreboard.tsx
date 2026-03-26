"use client";

import { useState, useEffect, useRef } from "react";
import { Trophy, Crown, TrendingUp, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, getInitials, cn } from "@/lib/utils";
import { createClient } from "@/lib/supabase";
import { useCRMStore } from "@/store/crm-store";
import { canManageTeam } from "@/lib/auth";

type TimePeriod = "this_month" | "last_month" | "this_quarter";

interface RepScore {
  id: string;
  name: string;
  closes: number;
  target: number;
  commission: number;
  streak: number;
  atRisk14Day: boolean;
  rank: number;
}

interface FeedItem {
  id: string;
  text: string;
  amount: number;
  time: string;
}

export function LiveScoreboard() {
  const { user } = useCRMStore();
  const [period, setPeriod] = useState<TimePeriod>("this_month");
  const [scores, setScores] = useState<RepScore[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [teamTarget, setTeamTarget] = useState({ current: 14, target: 25 });
  const [loading, setLoading] = useState(true);
  const supabaseRef = useRef(createClient());

  useEffect(() => {
    // Load initial scores
    loadScores();

    // Subscribe to realtime updates
    const subscription = supabaseRef.current
      .channel("scoreboard")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "commissions" },
        (payload) => {
          // Refresh scores on new commission
          loadScores();
          // Add to feed
          const newFeed: FeedItem = {
            id: payload.new.id,
            text: "New close recorded",
            amount: payload.new.amount,
            time: new Date().toISOString(),
          };
          setFeed((prev) => [newFeed, ...prev.slice(0, 19)]);
        }
      )
      .subscribe();

    return () => {
      subscription.unsubscribe();
    };
  }, [period]);

  const loadScores = async () => {
    setLoading(true);
    // Mock data — in production, fetch from API
    await new Promise((r) => setTimeout(r, 600));

    const mockScores: RepScore[] = [
      { id: "1", name: "Jordan K.", closes: 5, target: 5, commission: 1485, streak: 3, atRisk14Day: false, rank: 1 },
      { id: "2", name: "Alex M.", closes: 4, target: 5, commission: 1188, streak: 1, atRisk14Day: false, rank: 2 },
      { id: "3", name: "Sarah L.", closes: 3, target: 5, commission: 891, streak: 2, atRisk14Day: false, rank: 3 },
      { id: "4", name: "Mike T.", closes: 1, target: 5, commission: 297, streak: 0, atRisk14Day: true, rank: 4 },
      { id: "5", name: "Emma R.", closes: 1, target: 5, commission: 297, streak: 0, atRisk14Day: true, rank: 5 },
    ];

    setScores(mockScores);
    setFeed([
      { id: "f1", text: "Jordan closed Maple Tech on Shield", amount: 199, time: new Date(Date.now() - 600000).toISOString() },
      { id: "f2", text: "Alex closed NorthShore Dental on Starter", amount: 99, time: new Date(Date.now() - 3600000).toISOString() },
      { id: "f3", text: "Sarah closed Canuck Solutions on Enterprise", amount: 399, time: new Date(Date.now() - 7200000).toISOString() },
    ]);
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  const teamProgress = (teamTarget.current / teamTarget.target) * 100;
  const atTarget = teamProgress >= 100;

  const myScore = user ? scores.find((s) => s.name.includes(user.name.split(" ")[0])) : null;

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

        {/* Time period toggle */}
        <div className="flex items-center gap-1 bg-surface-2 border border-border rounded-lg p-1">
          {(["this_month", "last_month", "this_quarter"] as TimePeriod[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                period === p
                  ? "bg-surface-3 text-text-primary"
                  : "text-text-dim hover:text-text-secondary"
              )}
            >
              {p === "this_month" ? "This Month" : p === "last_month" ? "Last Month" : "This Quarter"}
            </button>
          ))}
        </div>
      </div>

      {/* Team target bar */}
      <div className={cn(
        "rounded-xl border p-4",
        atTarget ? "border-yellow/30 bg-yellow/5" : "border-border bg-surface-1"
      )}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {atTarget && <Crown className="w-4 h-4 text-yellow" />}
            <span className="text-sm font-semibold text-text-primary">
              Team Target — {teamTarget.current} / {teamTarget.target} closes
            </span>
          </div>
          <span className={cn(
            "text-sm font-bold",
            atTarget ? "text-yellow" : "text-text-primary"
          )}>
            {Math.round(teamProgress)}%
          </span>
        </div>
        <div className="h-3 bg-surface-3 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-1000",
              atTarget
                ? "bg-gradient-to-r from-yellow to-orange"
                : "bg-gradient-to-r from-accent to-accent-light"
            )}
            style={{ width: `${Math.min(100, teamProgress)}%` }}
          />
        </div>
        {!atTarget && (
          <p className="text-xs text-text-dim mt-1">
            {teamTarget.target - teamTarget.current} closes to team target
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Rankings */}
        <div className="lg:col-span-2">
          <div className="space-y-2">
            {scores.map((rep) => {
              const isMe = myScore?.id === rep.id;
              const progress = (rep.closes / rep.target) * 100;

              return (
                <div
                  key={rep.id}
                  className={cn(
                    "flex items-center gap-3 p-3.5 rounded-xl border transition-all",
                    isMe
                      ? "border-accent/40 bg-accent/5"
                      : "border-border bg-surface-1"
                  )}
                >
                  {/* Rank */}
                  <div className={cn(
                    "w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm",
                    rep.rank === 1 ? "bg-yellow/20 text-yellow" :
                    rep.rank === 2 ? "bg-surface-3 text-text-secondary" :
                    rep.rank === 3 ? "bg-orange/20 text-orange" :
                    "bg-surface-3 text-text-dim"
                  )}>
                    {rep.rank === 1 ? <Crown className="w-3.5 h-3.5" /> : `#${rep.rank}`}
                  </div>

                  {/* Avatar */}
                  <Avatar className="w-8 h-8 flex-shrink-0">
                    <AvatarFallback className="text-xs">{getInitials(rep.name)}</AvatarFallback>
                  </Avatar>

                  {/* Name + progress */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={cn("text-sm font-medium", isMe ? "text-accent-light" : "text-text-primary")}>
                        {rep.name}
                        {isMe && <span className="text-text-dim font-normal"> (you)</span>}
                      </span>
                      {rep.streak > 0 && (
                        <span className="text-2xs text-orange bg-orange/10 px-1.5 py-0.5 rounded">
                          🔥 {rep.streak}
                        </span>
                      )}
                      {user && canManageTeam(user) && rep.atRisk14Day && (
                        <Badge variant="warning" className="text-2xs">
                          <AlertTriangle className="w-2.5 h-2.5" /> 14-day
                        </Badge>
                      )}
                    </div>
                    <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all",
                          progress >= 100 ? "bg-green" : "bg-accent"
                        )}
                        style={{ width: `${Math.min(100, progress)}%` }}
                      />
                    </div>
                  </div>

                  {/* Stats */}
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

          {myScore && (
            <div className="mt-3 p-3 rounded-xl border border-accent/20 bg-accent/5 text-center">
              <p className="text-xs text-text-secondary">
                You are <span className="font-bold text-accent-light">
                  #{myScore.rank}
                </span> — {myScore.target - myScore.closes > 0 ? (
                  <>{myScore.target - myScore.closes} closes to hit your target</>
                ) : (
                  <>You hit your target! 🎉</>
                )}
              </p>
            </div>
          )}
        </div>

        {/* Live feed */}
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
                      <p className="text-2xs text-green font-medium">{formatCurrency(item.amount)}/mo</p>
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
