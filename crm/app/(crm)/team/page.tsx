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

  const MOCK_PERFORMANCE = {
    closes_this_month: 3,
    monthly_target: 5,
    conversion_rate: 24,
    avg_days_to_close: 14,
    commission_earned: 891,
    rank: 1,
    days_since_last_close: 3,
    at_risk_14_day: false,
  };

  const MOCK_AT_RISK_PERFORMANCE = {
    closes_this_month: 0,
    monthly_target: 5,
    conversion_rate: 8,
    avg_days_to_close: 21,
    commission_earned: 0,
    rank: 5,
    days_since_last_close: 17,
    at_risk_14_day: true,
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const result = await usersApi.list();
        if (result.success && result.data) {
          setReps(result.data.filter((u) => u.role === "rep" || u.role === "team_lead"));
        } else {
          // Use mock users
          setReps([
            { id: "u1", name: "Jordan K.", email: "jordan@hawk.ca", role: "rep", team_lead_id: null, status: "active", last_close_at: new Date(Date.now() - 259200000).toISOString(), whatsapp_number: null, invited_by: null, created_at: new Date().toISOString() },
            { id: "u2", name: "Alex M.", email: "alex@hawk.ca", role: "rep", team_lead_id: null, status: "active", last_close_at: new Date(Date.now() - 432000000).toISOString(), whatsapp_number: null, invited_by: null, created_at: new Date().toISOString() },
            { id: "u3", name: "Mike T.", email: "mike@hawk.ca", role: "rep", team_lead_id: null, status: "at_risk", last_close_at: new Date(Date.now() - 1468800000).toISOString(), whatsapp_number: null, invited_by: null, created_at: new Date().toISOString() },
          ]);
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
              performance={rep.status === "at_risk" ? MOCK_AT_RISK_PERFORMANCE : MOCK_PERFORMANCE}
              canManage={canManage}
              onAtRiskAction={(action) => handleAtRiskAction(rep.id, action)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
