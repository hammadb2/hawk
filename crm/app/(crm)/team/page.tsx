"use client";

import { useState, useEffect } from "react";
import { Users } from "lucide-react";
import { RepCard } from "@/components/team/rep-card";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { useCRMStore } from "@/store/crm-store";
import { usersApi } from "@/lib/api";
import { getSupabaseClient } from "@/lib/supabase";
import { toast } from "@/components/ui/toast";
import { canManageTeam } from "@/lib/auth";
import type { CRMUser } from "@/types/crm";

type PerformanceRow = {
  closes_this_month: number;
  monthly_target: number;
  commission_earned: number;
  at_risk_14_day: boolean;
  rank: number;
  conversion_rate: number;
  avg_days_to_close: number;
  days_since_last_close: number;
};

export default function TeamPage() {
  const { user } = useCRMStore();
  const [reps, setReps] = useState<CRMUser[]>([]);
  const [loading, setLoading] = useState(false);

  const [performances, setPerformances] = useState<Record<string, PerformanceRow>>({});

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const result = await usersApi.list();
        if (result.success && result.data) {
          const teamMembers = result.data.filter((u) => u.role === "rep" || u.role === "team_lead" || u.role === "csm");
          setReps(teamMembers);

          const supabase = getSupabaseClient();
          const now = new Date();
          const monthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
          const { data: comms } = await supabase.from("commissions").select("rep_id, type, amount").eq("month_year", monthYear);

          type Row = {
            rep: CRMUser;
            closes: number;
            commission: number;
            daysSince: number;
            at_risk_14_day: boolean;
          };

          const rows: Row[] = teamMembers.map((rep) => {
            const repComms = (comms ?? []).filter((c) => c.rep_id === rep.id);
            const closes = repComms.filter((c) => c.type === "closing").length;
            const commission = repComms.reduce((s, c) => s + (c.amount || 0), 0);
            const lastClose = rep.last_close_at ? new Date(rep.last_close_at) : null;
            const daysSince = lastClose ? Math.floor((Date.now() - lastClose.getTime()) / 86400000) : 999;
            return {
              rep,
              closes,
              commission,
              daysSince,
              at_risk_14_day: rep.status === "at_risk" || daysSince >= 14,
            };
          });

          rows.sort((a, b) => b.closes - a.closes || b.commission - a.commission);

          const perfMap: Record<string, PerformanceRow> = {};
          rows.forEach((row, idx) => {
            perfMap[row.rep.id] = {
              closes_this_month: row.closes,
              monthly_target: 5,
              commission_earned: row.commission,
              at_risk_14_day: row.at_risk_14_day,
              rank: idx + 1,
              conversion_rate: 0,
              avg_days_to_close: 0,
              days_since_last_close: row.daysSince,
            };
          });
          setPerformances(perfMap);
        } else {
          toast({ title: "Failed to load team", variant: "destructive" });
        }
      } catch {
        toast({ title: "Failed to load team", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const handleAtRiskAction = async (
    repId: string,
    action: "extend_7d" | "begin_removal" | "on_leave"
  ) => {
    try {
      await usersApi.updateStatus(
        repId,
        action === "begin_removal" ? "inactive" : "at_risk",
        action
      );
      toast({ title: `Action applied: ${action.replace(/_/g, " ")}`, variant: "success" });
    } catch {
      toast({ title: "Failed to apply action", variant: "destructive" });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  const canManage = user ? canManageTeam(user) : false;

  const defaultPerformance: PerformanceRow = {
    closes_this_month: 0,
    monthly_target: 5,
    commission_earned: 0,
    at_risk_14_day: false,
    rank: 0,
    conversion_rate: 0,
    avg_days_to_close: 0,
    days_since_last_close: 0,
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-text-primary">Team</h1>
        <p className="text-sm text-text-secondary mt-0.5">{reps.length} active members</p>
      </div>

      {reps.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No team members yet"
          description="Invite reps from Settings to build your team."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {reps.map((rep) => (
            <RepCard
              key={rep.id}
              rep={rep}
              performance={performances[rep.id] ?? defaultPerformance}
              canManage={canManage}
              onAtRiskAction={(action) => handleAtRiskAction(rep.id, action)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
