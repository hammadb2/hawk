"use client";

import { useState, useEffect } from "react";
import { Users } from "lucide-react";
import { RepCard } from "@/components/team/rep-card";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { useCRMStore } from "@/store/crm-store";
import { usersApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { canManageTeam } from "@/lib/auth";
import type { CRMUser } from "@/types/crm";

export default function TeamPage() {
  const { user } = useCRMStore();
  const [reps, setReps] = useState<CRMUser[]>([]);
  const [loading, setLoading] = useState(true);

  const [performances, setPerformances] = useState<Record<string, {
    closes_this_month: number; monthly_target: number; commission_earned: number;
    at_risk_14_day: boolean; rank: number;
  }>>({});

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const result = await usersApi.list();
        if (result.success && result.data) {
          const teamMembers = result.data.filter((u) => u.role === "rep" || u.role === "team_lead" || u.role === "csm");
          setReps(teamMembers);

          // Load commission data for this month
          const { createClient } = await import("@/lib/supabase");
          const supabase = createClient();
          const now = new Date();
          const monthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
          const { data: comms } = await supabase.from("commissions").select("rep_id, type, amount").eq("month_year", monthYear);

          const perfMap: typeof performances = {};
          teamMembers.forEach((rep, idx) => {
            const repComms = (comms ?? []).filter((c) => c.rep_id === rep.id);
            const closes = repComms.filter((c) => c.type === "closing").length;
            const commission = repComms.reduce((s, c) => s + (c.amount || 0), 0);
            const lastClose = rep.last_close_at ? new Date(rep.last_close_at) : null;
            const daysSince = lastClose ? Math.floor((Date.now() - lastClose.getTime()) / 86400000) : 999;
            perfMap[rep.id] = {
              closes_this_month: closes,
              monthly_target: 5,
              commission_earned: commission,
              at_risk_14_day: rep.status === "at_risk" || daysSince >= 14,
              rank: idx + 1,
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
    load();
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
              performance={performances[rep.id] ?? { closes_this_month: 0, monthly_target: 5, commission_earned: 0, at_risk_14_day: false, rank: 0, conversion_rate: 0, avg_days_to_close: 0, days_since_last_close: 0 }}
              canManage={canManage}
              onAtRiskAction={(action) => handleAtRiskAction(rep.id, action)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
