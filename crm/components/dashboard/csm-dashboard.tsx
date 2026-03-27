"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Calendar, TrendingUp, CheckSquare, Users, ArrowUpRight } from "lucide-react";
import { Client, OnboardingTask, ClientHealthSync, ChurnRisk } from "@/types/crm";
import { getSupabaseClient } from "@/lib/supabase";
import { useAuthReady } from "@/components/layout/providers";
import { cn, formatDate, formatCurrency, formatRelativeTime } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CSMClientRow extends Client {
  health: ClientHealthSync | null;
  overdue_tasks: number;
  total_tasks: number;
  completed_tasks: number;
  company_name: string | null;
  churn_risk_numeric: number;
}

interface RenewalItem {
  client_id: string;
  company_name: string;
  renewal_date: string;
  mrr: number;
  plan: string;
  days_until: number;
}

// ─── Risk Badge ───────────────────────────────────────────────────────────────

const RISK_COLORS: Record<ChurnRisk, string> = {
  low:      "text-green-400 bg-green-400/10",
  medium:   "text-yellow-400 bg-yellow-400/10",
  high:     "text-orange-400 bg-orange-400/10",
  critical: "text-red-400 bg-red-500/10",
};

function RiskBadge({ risk, score }: { risk: ChurnRisk; score: number }) {
  return (
    <span
      className={cn("px-2 py-0.5 rounded-full text-xs font-medium cursor-default capitalize", RISK_COLORS[risk])}
      title={`Score: ${score}/100`}
    >
      {risk} ({score})
    </span>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, icon }: { label: string; value: string | number; sub?: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-surface-3 bg-surface-1 p-5">
      <div className="flex items-center gap-2 text-text-dim mb-3">
        {icon}
        <span className="text-xs uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold text-text-primary">{value}</p>
      {sub && <p className="text-xs text-text-dim mt-1">{sub}</p>}
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export function CSMDashboard({ csmId }: { csmId: string }) {
  const authReady = useAuthReady();
  const [clients, setClients] = useState<CSMClientRow[]>([]);
  const [renewals, setRenewals] = useState<RenewalItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!authReady) return;
    loadData();
  }, [authReady, csmId]);

  async function loadData() {
    setLoading(true);
    try {
      const sb = getSupabaseClient();

      // Load assigned clients
      const clientsRes = await sb
        .from("clients")
        .select("*")
        .eq("csm_rep_id", csmId)
        .eq("status", "active");

      const rawClients = clientsRes.data ?? [];

      // Load onboarding task counts per client
      const clientIds = rawClients.map((c) => c.id);
      let taskCounts: Record<string, { overdue: number; total: number; completed: number }> = {};

      if (clientIds.length > 0) {
        const tasksRes = await sb
          .from("onboarding_tasks")
          .select("client_id, status, due_date")
          .in("client_id", clientIds);

        for (const t of tasksRes.data ?? []) {
          if (!taskCounts[t.client_id]) {
            taskCounts[t.client_id] = { overdue: 0, total: 0, completed: 0 };
          }
          taskCounts[t.client_id].total++;
          if (t.status === "completed") taskCounts[t.client_id].completed++;
          if (t.status === "pending" && new Date(t.due_date) < new Date()) {
            taskCounts[t.client_id].overdue++;
          }
        }
      }

      const enriched: CSMClientRow[] = rawClients.map((c: any) => ({
        ...c,
        health: null,
        overdue_tasks: taskCounts[c.id]?.overdue ?? 0,
        total_tasks: taskCounts[c.id]?.total ?? 0,
        completed_tasks: taskCounts[c.id]?.completed ?? 0,
      }));

      setClients(enriched);

      // Build renewals in next 30 days from health sync
      const upcoming: RenewalItem[] = enriched
        .filter((c) => c.health?.renewal_date)
        .map((c) => ({
          client_id: c.id,
          company_name: c.company_name ?? "",
          renewal_date: c.health!.renewal_date!,
          mrr: c.mrr ?? 0,
          plan: c.plan ?? "",
          days_until: Math.ceil(
            (new Date(c.health!.renewal_date!).getTime() - Date.now()) / 86400000,
          ),
        }))
        .filter((r) => r.days_until >= 0 && r.days_until <= 30)
        .sort((a, b) => a.days_until - b.days_until);

      setRenewals(upcoming);
    } finally {
      setLoading(false);
    }
  }

  // Computed stats
  const totalMRR = clients.reduce((s, c) => s + (c.mrr ?? 0), 0);
  const criticalCount = clients.filter((c) => c.churn_risk_score === "critical").length;
  const highCount = clients.filter((c) => c.churn_risk_score === "high").length;
  const avgOnboarding = clients.length
    ? Math.round(clients.reduce((s, c) => s + (c.health?.onboarding_pct ?? 0), 0) / clients.length)
    : 0;
  const overdueTaskCount = clients.reduce((s, c) => s + c.overdue_tasks, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-8 h-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">CSM Dashboard</h1>
        <p className="text-text-secondary text-sm mt-1">
          {clients.length} active client{clients.length !== 1 ? "s" : ""} assigned to you
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Book MRR"
          value={formatCurrency(totalMRR)}
          sub="active clients"
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatCard
          label="At-Risk"
          value={criticalCount + highCount}
          sub={`${criticalCount} critical, ${highCount} high`}
          icon={<AlertTriangle className="w-4 h-4" />}
        />
        <StatCard
          label="Renewals / 30d"
          value={renewals.length}
          sub={renewals.length > 0 ? `Next: ${renewals[0].company_name}` : "None upcoming"}
          icon={<Calendar className="w-4 h-4" />}
        />
        <StatCard
          label="Avg Onboarding"
          value={`${avgOnboarding}%`}
          sub={overdueTaskCount > 0 ? `${overdueTaskCount} overdue tasks` : "On track"}
          icon={<CheckSquare className="w-4 h-4" />}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Client Health Table */}
        <div className="lg:col-span-2 rounded-xl border border-surface-3 bg-surface-1 overflow-hidden">
          <div className="px-6 py-4 border-b border-surface-3 flex items-center justify-between">
            <h2 className="font-semibold text-text-primary flex items-center gap-2">
              <Users className="w-4 h-4 text-accent" />
              Clients by Risk
            </h2>
            <span className="text-xs text-text-dim">{clients.length} total</span>
          </div>
          <div className="divide-y divide-surface-3">
            {clients.length === 0 && (
              <p className="px-6 py-8 text-sm text-text-dim text-center">
                No active clients assigned to you yet.
              </p>
            )}
            {clients.map((client) => {
              const onbPct = client.health?.onboarding_pct ?? 0;
              const taskPct = client.total_tasks
                ? Math.round((client.completed_tasks / client.total_tasks) * 100)
                : null;
              return (
                <div
                  key={client.id}
                  className={cn(
                    "px-6 py-4 hover:bg-surface-2 transition-colors",
                    client.churn_risk_score === "critical" && "border-l-2 border-red-500",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-text-primary truncate">{client.company_name}</p>
                      <p className="text-xs text-text-dim mt-0.5">
                        {client.plan} · {formatCurrency(client.mrr ?? 0)}/mo
                        {client.health?.last_login_date && (
                          <> · Login {formatRelativeTime(client.health.last_login_date)}</>
                        )}
                      </p>
                    </div>
                    <RiskBadge
                      risk={(client.churn_risk_score as ChurnRisk) ?? "low"}
                      score={client.churn_risk_numeric ?? 0}
                    />
                  </div>

                  {/* Progress bars */}
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div>
                      <div className="flex justify-between text-xs text-text-dim mb-1">
                        <span>Onboarding</span>
                        <span>{onbPct}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
                        <div
                          className={cn("h-full rounded-full", onbPct < 50 ? "bg-red-400" : "bg-accent")}
                          style={{ width: `${onbPct}%` }}
                        />
                      </div>
                    </div>
                    {taskPct !== null && (
                      <div>
                        <div className="flex justify-between text-xs text-text-dim mb-1">
                          <span>Tasks</span>
                          <span className={cn(client.overdue_tasks > 0 && "text-red-400")}>
                            {client.completed_tasks}/{client.total_tasks}
                            {client.overdue_tasks > 0 && ` (${client.overdue_tasks} overdue)`}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
                          <div
                            className={cn("h-full rounded-full", client.overdue_tasks > 0 ? "bg-orange-400" : "bg-green-400")}
                            style={{ width: `${taskPct}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Alert flags */}
                  {(client.health?.cancellation_intent || client.health?.payment_failed_count! > 0) && (
                    <div className="mt-2 flex gap-2">
                      {client.health?.cancellation_intent && (
                        <span className="text-xs text-red-400">🚨 Cancellation intent</span>
                      )}
                      {client.health?.payment_failed_count! > 0 && (
                        <span className="text-xs text-orange-400">
                          ⚠ {client.health?.payment_failed_count} payment failure(s)
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Upcoming Renewals */}
        <div className="rounded-xl border border-surface-3 bg-surface-1 overflow-hidden">
          <div className="px-6 py-4 border-b border-surface-3">
            <h2 className="font-semibold text-text-primary flex items-center gap-2">
              <Calendar className="w-4 h-4 text-accent" />
              Renewals (30 days)
            </h2>
          </div>
          <div className="divide-y divide-surface-3">
            {renewals.length === 0 && (
              <p className="px-6 py-8 text-sm text-text-dim text-center">No renewals in the next 30 days.</p>
            )}
            {renewals.map((r) => (
              <div key={r.client_id} className="px-6 py-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-text-primary truncate">{r.company_name}</p>
                  <span className={cn(
                    "text-xs font-medium",
                    r.days_until <= 7 ? "text-red-400" : r.days_until <= 14 ? "text-orange-400" : "text-text-dim",
                  )}>
                    {r.days_until}d
                  </span>
                </div>
                <p className="text-xs text-text-dim mt-0.5">
                  {r.plan} · {formatCurrency(r.mrr)}/mo · {formatDate(r.renewal_date)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
