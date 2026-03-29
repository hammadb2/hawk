"use client";

import { useState, useEffect } from "react";
import { Users, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, cn, withTimeout } from "@/lib/utils";
import { getSupabaseClient } from "@/lib/supabase";

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

      const [usersRes, commissionsRes, clientsRes, prospectsRes] = await withTimeout(
        Promise.all([
          supabase.from("users").select("id, name, status, last_close_at").in("role", ["rep", "team_lead"]),
          supabase.from("commissions").select("rep_id, type, amount").eq("month_year", monthYear),
          supabase.from("clients").select("mrr, close_date").eq("status", "active"),
          supabase.from("prospects").select("id"),
        ]),
        25_000,
        "HoS dashboard"
      );

      const allReps = usersRes.data ?? [];
      const commissions = commissionsRes.data ?? [];
      const activeClients = clientsRes.data ?? [];
      const allProspects = prospectsRes.data ?? [];

      const teamCloses = commissions.filter((c) => c.type === "closing").length;
      const mrrAdded = activeClients
        .filter((c) => c.close_date && c.close_date >= startOfMonth)
        .reduce((s, c) => s + (c.mrr || 0), 0);
      const totalPipeline = allProspects.length * 149;

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
    } catch {
      // fail silently — show empty state
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
        <StatCard label="Total Pipeline" value={formatCurrency(stats.totalPipeline)} />
        <StatCard label="Avg Close Rate" value={reps.length > 0 ? `${Math.round((totalCloses / Math.max(1, reps.length * 5)) * 100)}%` : "0%"} />
        <StatCard label="MRR Added" value={formatCurrency(stats.mrrAdded)} />
      </div>

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
                  <span className={cn(
                    "text-sm font-bold w-5 text-center",
                    i === 0 ? "text-yellow" : "text-text-dim"
                  )}>
                    #{i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-text-primary">{rep.name}</span>
                      {rep.atRisk && <Badge variant="warning" className="text-2xs">At Risk</Badge>}
                    </div>
                    <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                      <div
                        className={cn("h-full rounded-full", rep.closes >= rep.target ? "bg-green" : "bg-accent")}
                        style={{ width: `${Math.min(100, (rep.closes / rep.target) * 100)}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-semibold text-text-primary">{rep.closes}/{rep.target}</p>
                    <p className="text-2xs text-text-dim">{formatCurrency(rep.commission)}</p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

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
      </div>
    </div>
  );
}
