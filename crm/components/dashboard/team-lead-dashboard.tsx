"use client";

import { useState, useEffect } from "react";
import { Users, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, formatRelativeTime, cn } from "@/lib/utils";
import { useCRMStore } from "@/store/crm-store";
import { getSupabaseClient } from "@/lib/supabase";
import { useAuthReady } from "@/components/layout/providers";

interface RepRow {
  id: string;
  name: string;
  status: string;
  last_close_at: string | null;
  closes: number;
  target: number;
}

export function TeamLeadDashboard() {
  const authReady = useAuthReady();
  const { user } = useCRMStore();
  const [loading, setLoading] = useState(false);
  const [teamReps, setTeamReps] = useState<RepRow[]>([]);
  const [stats, setStats] = useState({ teamCloses: 0, ownCloses: 0, overrideEarned: 0, teamPipeline: 0 });

  useEffect(() => {
    if (!authReady) return;
    load();
  }, [authReady]);

  const load = async () => {
    setLoading(true);
    try {
      const supabase = getSupabaseClient();

      // Get user ID directly from auth — don't depend on store timing
      const { data: { user: authUser } } = await supabase.auth.getUser();
      if (!authUser) return;

      const now = new Date();
      const monthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
      const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();

      const [repsRes, commissionsRes, pipelineRes] = await Promise.all([
        supabase.from("users").select("id, name, status, last_close_at").eq("team_lead_id", authUser.id).in("role", ["rep"]),
        supabase.from("commissions").select("rep_id, type, amount, month_year").eq("month_year", monthYear),
        supabase.from("prospects").select("id, assigned_rep_id").not("stage", "in", '("closed_won","lost")'),
      ]);

      const reps = repsRes.data ?? [];
      const commissions = commissionsRes.data ?? [];
      const pipeline = pipelineRes.data ?? [];

      const repIds = reps.map((r) => r.id);

      // Team closes this month (closing commissions for team reps)
      const teamCommissions = commissions.filter((c) => repIds.includes(c.rep_id) && c.type === "closing");
      const teamCloses = teamCommissions.length;

      // Own closes this month
      const ownCommissions = commissions.filter((c) => c.rep_id === authUser.id && c.type === "closing");
      const ownCloses = ownCommissions.length;

      // Override earned: 5% of closing commission amounts for team reps
      const overrideEarned = teamCommissions.reduce((s, c) => s + (c.amount || 0) * 0.05, 0);

      // Team pipeline (count of active prospects for team reps)
      const teamPipeline = pipeline.filter((p) => repIds.includes(p.assigned_rep_id)).length;

      setStats({ teamCloses, ownCloses, overrideEarned, teamPipeline });

      // Build rep rows with close counts
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
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  };

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
        <h1 className="text-xl font-bold text-text-primary">Team Dashboard</h1>
        <p className="text-sm text-text-secondary mt-0.5">Your team's performance.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Team Closes" value={String(stats.teamCloses)} subValue="This month" accent />
        <StatCard label="Your Closes" value={String(stats.ownCloses)} />
        <StatCard label="Override Earned" value={formatCurrency(stats.overrideEarned)} />
        <StatCard label="Active Pipeline" value={`${stats.teamPipeline} prospects`} />
      </div>

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
              <div key={rep.id} className={cn(
                "flex items-center gap-3 p-3 rounded-lg border transition-all",
                rep.status === "at_risk" ? "border-red/30 bg-red/5" : "border-border bg-surface-2"
              )}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-text-primary">{rep.name}</span>
                    {rep.status === "at_risk" && <Badge variant="destructive" className="text-2xs">14-Day Risk</Badge>}
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
                  <p className="text-sm font-semibold text-text-primary">{rep.closes}/{rep.target}</p>
                  <p className="text-2xs text-text-dim">
                    {rep.last_close_at ? `Last: ${formatRelativeTime(rep.last_close_at)}` : "No closes yet"}
                  </p>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
