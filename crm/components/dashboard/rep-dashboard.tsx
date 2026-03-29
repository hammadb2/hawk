"use client";

import { useState, useEffect } from "react";
import { Phone, Video, Scan, Target, DollarSign, CheckSquare, Flame, Trophy, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import { useCRMStore } from "@/store/crm-store";
import { formatCurrency, formatRelativeTime, stageLabel, cn, withTimeout } from "@/lib/utils";
import type { Prospect } from "@/types/crm";

interface DailyNonNeg {
  label: string;
  icon: typeof Phone;
  current: number;
  target: number;
  key: string;
}

export function RepDashboard() {
  const { user, prospects } = useCRMStore();
  const [authUserId, setAuthUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState({
    closesThisMonth: 0,
    monthlyTarget: 5,
    commissionEarned: 0,
    calls: 0,
    looms: 0,
    scans: 0,
    rank: 0,
    totalReps: 0,
  });
  const [tasks, setTasks] = useState<Array<{
    id: string;
    title: string;
    dueTime: string;
    overdue: boolean;
    done: boolean;
  }>>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const { getSupabaseClient } = await import("@/lib/supabase");
        const supabase = getSupabaseClient();

        // Get user ID directly from auth — don't depend on store timing
        const { data: { user: authUser } } = await supabase.auth.getUser();
        if (!authUser) return;
        setAuthUserId(authUser.id);

        const now = new Date();
        const monthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

        const [commissionsRes, allRepsRes, activitiesRes] = await withTimeout(
          Promise.all([
            supabase.from("commissions").select("id, type, amount").eq("rep_id", authUser.id).eq("month_year", monthYear),
            supabase.from("users").select("id").in("role", ["rep", "team_lead"]),
            supabase.from("activities").select("id, type, created_at").eq("created_by", authUser.id).gte("created_at", new Date(now.getFullYear(), now.getMonth(), 1).toISOString()),
          ]),
          25_000,
          "Rep dashboard"
        );

        const comms = commissionsRes.data ?? [];
        const allReps = allRepsRes.data ?? [];
        const acts = activitiesRes.data ?? [];

        const closesThisMonth = comms.filter((c) => c.type === "closing").length;
        const commissionEarned = comms.reduce((s, c) => s + (c.amount || 0), 0);
        const calls = acts.filter((a) => a.type === "call").length;
        const looms = acts.filter((a) => a.type === "loom_sent").length;
        const scans = acts.filter((a) => a.type === "scan_run").length;

        const { data: allComms } = await supabase.from("commissions").select("rep_id, type").eq("month_year", monthYear).eq("type", "closing");
        const closesByRep: Record<string, number> = {};
        (allComms ?? []).forEach((c) => { closesByRep[c.rep_id] = (closesByRep[c.rep_id] || 0) + 1; });
        const rank = Object.values(closesByRep).filter((n) => n > closesThisMonth).length + 1;

        setStats({ closesThisMonth, monthlyTarget: 5, commissionEarned, calls, looms, scans, rank, totalReps: allReps.length });
        setTasks([]);
      } catch {
        // fail silently — show zeros
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const repId = authUserId ?? user?.id;
  const myProspects = prospects.filter((p) => p.assigned_rep_id === repId);
  const hotLeads = myProspects.filter((p) => p.is_hot && p.stage !== "closed_won" && p.stage !== "lost");

  const nonNegs: DailyNonNeg[] = [
    { label: "Calls Logged", icon: Phone, current: stats.calls, target: 10, key: "calls" },
    { label: "Looms Sent", icon: Video, current: stats.looms, target: 3, key: "looms" },
    { label: "Scans Run", icon: Scan, current: stats.scans, target: 5, key: "scans" },
  ];

  const closesProgress = (stats.closesThisMonth / stats.monthlyTarget) * 100;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">
          Good {getGreeting()}, {user?.name?.split(" ")[0]}
        </h1>
        <p className="text-sm text-text-secondary mt-0.5">Here's your day at a glance.</p>
      </div>

      {/* Daily Non-Negotiables */}
      <div>
        <h2 className="text-sm font-semibold text-text-secondary mb-3 uppercase tracking-wide">
          Daily Non-Negotiables
        </h2>
        <div className="grid grid-cols-3 gap-4">
          {nonNegs.map((item) => {
            const Icon = item.icon;
            const pct = Math.min(100, (item.current / item.target) * 100);
            const done = item.current >= item.target;
            return (
              <div
                key={item.key}
                className={cn(
                  "rounded-xl border p-4 transition-all",
                  done ? "border-green/30 bg-green/5" : "border-border bg-surface-1"
                )}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      "w-7 h-7 rounded-lg flex items-center justify-center",
                      done ? "bg-green/20" : "bg-surface-3"
                    )}>
                      <Icon className={cn("w-3.5 h-3.5", done ? "text-green" : "text-text-dim")} />
                    </div>
                    <span className="text-xs font-medium text-text-secondary">{item.label}</span>
                  </div>
                  <span className={cn("text-xs font-bold", done ? "text-green" : "text-text-primary")}>
                    {item.current}/{item.target}
                  </span>
                </div>
                <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                  <div
                    className={cn("h-full rounded-full transition-all", done ? "bg-green" : "bg-accent")}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-text-dim uppercase tracking-wide">
              Closes This Month
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-4">
              <div>
                <p className="text-4xl font-bold text-text-primary">{stats.closesThisMonth}</p>
                <p className="text-xs text-text-dim mt-1">of {stats.monthlyTarget} target</p>
              </div>
              <div className="flex-1 mb-1">
                <div className="h-2 bg-surface-3 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      closesProgress >= 100 ? "bg-green" : closesProgress >= 60 ? "bg-accent" : "bg-yellow"
                    )}
                    style={{ width: `${closesProgress}%` }}
                  />
                </div>
                <p className="text-xs text-text-dim mt-1">
                  {stats.monthlyTarget - stats.closesThisMonth} more to hit target
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <StatCard
          label="Commission Earned"
          value={formatCurrency(stats.commissionEarned)}
          subValue="This month"
          accent
        />

        <div className="rounded-xl border border-border bg-surface-1 p-4">
          <p className="text-xs font-medium text-text-dim mb-1">Your Rank</p>
          <div className="flex items-center gap-2">
            <Trophy className="w-5 h-5 text-yellow" />
            <span className="text-2xl font-bold text-text-primary">#{stats.rank}</span>
          </div>
          <p className="text-xs text-text-dim mt-1">of {stats.totalReps} reps</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Tasks */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckSquare className="w-4 h-4 text-accent-light" />
              Today's Tasks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {tasks.length === 0 ? (
              <EmptyState
                icon={CheckSquare}
                title="No tasks today"
                description="You're all caught up!"
                className="py-8"
              />
            ) : (
              tasks.map((task) => (
                <div
                  key={task.id}
                  className={cn(
                    "flex items-start gap-3 p-3 rounded-lg border transition-all",
                    task.overdue
                      ? "border-red/30 bg-red/5"
                      : "border-border bg-surface-2"
                  )}
                >
                  <input
                    type="checkbox"
                    checked={task.done}
                    onChange={() => {}}
                    className="mt-0.5 rounded border-border"
                  />
                  <div className="flex-1 min-w-0">
                    <p className={cn(
                      "text-sm",
                      task.done ? "text-text-dim line-through" : "text-text-primary"
                    )}>
                      {task.title}
                    </p>
                    <p className={cn(
                      "text-xs mt-0.5",
                      task.overdue ? "text-red font-medium" : "text-text-dim"
                    )}>
                      {task.overdue ? "Overdue — " : ""}{task.dueTime}
                    </p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Hot Leads */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Flame className="w-4 h-4 text-orange" />
              Hot Leads
              {hotLeads.length > 0 && (
                <Badge variant="warning" className="ml-auto">{hotLeads.length}</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {hotLeads.length === 0 ? (
              <EmptyState
                icon={Flame}
                title="No hot leads"
                description="Mark prospects as hot to track them here."
                className="py-8"
              />
            ) : (
              <div className="space-y-2">
                {hotLeads.slice(0, 5).map((p) => (
                  <HotLeadRow key={p.id} prospect={p} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* My Pipeline Snapshot */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue" />
            My Pipeline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PipelineSnapshot prospects={myProspects} />
        </CardContent>
      </Card>
    </div>
  );
}

function HotLeadRow({ prospect }: { prospect: Prospect }) {
  const { setSelectedProspect, setDrawerOpen } = useCRMStore();

  return (
    <div
      onClick={() => { setSelectedProspect(prospect); setDrawerOpen(true); }}
      className="flex items-center gap-3 p-2.5 rounded-lg border border-border bg-surface-2 hover:border-accent/40 transition-all cursor-pointer"
    >
      <HawkScoreRing score={prospect.hawk_score} size="sm" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary truncate">{prospect.company_name}</p>
        <p className="text-xs text-text-dim truncate">{prospect.domain}</p>
      </div>
      <Badge variant="secondary" className="text-2xs flex-shrink-0">
        {stageLabel(prospect.stage)}
      </Badge>
    </div>
  );
}

function PipelineSnapshot({ prospects }: { prospects: Prospect[] }) {
  const stages = [
    "new", "scanned", "loom_sent", "replied", "call_booked", "proposal_sent"
  ] as const;

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
      {stages.map((stage) => {
        const count = prospects.filter((p) => p.stage === stage).length;
        return (
          <div key={stage} className="text-center">
            <div className="text-xl font-bold text-text-primary">{count}</div>
            <div className="text-2xs text-text-dim mt-0.5 leading-tight">{stageLabel(stage)}</div>
          </div>
        );
      })}
    </div>
  );
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}
