"use client";

import { useState, useEffect } from "react";
import { DollarSign, Clock, TrendingUp, Download, ExternalLink, Building2 } from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { commissionsApi, clientsApi, usersApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { formatCurrency, downloadCSV, daysUntil, cn, formatDate } from "@/lib/utils";
import {
  calculateMonthlyTotal,
  getNextBonusTier,
  calculateResidualCommission,
  clawbackDaysRemaining,
} from "@/lib/commission";
import type { Commission, Client, UserRole } from "@/types/crm";

const PIE_COLORS = {
  closing: "#7B5CF5",
  residual: "#34D399",
  bonus: "#FBBF24",
  override: "#60A5FA",
};

function clawbackDaysForCommission(c: Commission): number {
  const cl = c.client;
  if (cl?.clawback_deadline) return daysUntil(cl.clawback_deadline);
  if (cl?.close_date) return clawbackDaysRemaining(new Date(cl.close_date));
  return clawbackDaysRemaining(new Date(c.calculated_at));
}

function last12MonthBars(history: Commission[]) {
  const earnedByMonth: Record<string, number> = {};
  history.forEach((c) => {
    earnedByMonth[c.month_year] = (earnedByMonth[c.month_year] || 0) + c.amount;
  });
  const now = new Date();
  const out: { month: string; earned: number }[] = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    out.push({
      month: d.toLocaleString("default", { month: "short" }),
      earned: earnedByMonth[key] ?? 0,
    });
  }
  return out;
}

export function MyEarnings() {
  const [commissions, setCommissions] = useState<Commission[]>([]);
  const [historyCommissions, setHistoryCommissions] = useState<Commission[]>([]);
  const [activeClients, setActiveClients] = useState<Client[]>([]);
  const [userRole, setUserRole] = useState<UserRole>("rep");
  const [loading, setLoading] = useState(false);
  const [monthYear] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const me = await usersApi.me();
        if (!me.success || !me.data) {
          toast({ title: me.error || "Could not load profile", variant: "destructive" });
          return;
        }
        setUserRole(me.data.role);
        const uid = me.data.id;

        const [monthRes, histRes, clientsRes] = await Promise.all([
          commissionsApi.myEarnings(monthYear),
          commissionsApi.myEarnings(undefined, { limit: 500 }),
          clientsApi.list({ status: "active", rep_id: uid }),
        ]);

        if (monthRes.success && monthRes.data) setCommissions(monthRes.data);
        if (histRes.success && histRes.data) setHistoryCommissions(histRes.data);
        if (clientsRes.success && clientsRes.data) setActiveClients(clientsRes.data);
      } catch {
        toast({ title: "Failed to load earnings", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [monthYear]);

  const totals = calculateMonthlyTotal(commissions);
  const closesThisMonth = commissions.filter((c) => c.type === "closing").length;
  const bonusTier = getNextBonusTier(closesThisMonth);

  const pieData = [
    { name: "Closing", value: totals.closing, color: PIE_COLORS.closing },
    { name: "Residual", value: totals.residual, color: PIE_COLORS.residual },
    { name: "Bonus", value: totals.bonus, color: PIE_COLORS.bonus },
    { name: "Override", value: totals.override, color: PIE_COLORS.override },
  ].filter((d) => d.value > 0);

  const historyData = last12MonthBars(historyCommissions);

  const handleExportLocal = () => {
    downloadCSV(
      commissions.map((c) => ({
        type: c.type,
        amount: c.amount,
        status: c.status,
        month: c.month_year,
        calculated_at: c.calculated_at,
        client: c.client?.prospect?.company_name ?? "",
      })),
      `hawk-commissions-${monthYear}.csv`
    );
    toast({ title: "CSV exported", variant: "success" });
  };

  const handleDeelExport = async () => {
    const r = await commissionsApi.exportCSV(monthYear);
    if (r.success && r.data?.url) {
      window.open(r.data.url, "_blank", "noopener,noreferrer");
      toast({ title: "Opening Deel export", variant: "success" });
    } else {
      handleExportLocal();
      toast({
        title: r.error ? "Deel export unavailable — downloaded local CSV" : "Downloaded local CSV",
        variant: "success",
      });
    }
  };

  const clawbackRows = commissions.filter((c) => c.type === "closing" && c.status === "pending");

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-text-primary">My Earnings</h1>
          <p className="text-sm text-text-secondary">Commission breakdown for {monthYear}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={handleExportLocal} className="gap-1.5">
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void handleDeelExport()} className="gap-1.5">
            <ExternalLink className="w-3.5 h-3.5" />
            Deel export
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Earned" value={formatCurrency(totals.net)} accent />
        <StatCard
          label="Status"
          value={
            totals.clawback > 0
              ? "At Risk"
              : commissions.some((c) => c.status === "paid")
                ? "Paid"
                : "Pending"
          }
        />
        <StatCard label="Closing" value={formatCurrency(totals.closing)} />
        <StatCard label="Residual" value={formatCurrency(totals.residual)} />
      </div>

      {/* Active clients → residual stream */}
      {activeClients.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-accent-light" />
              Residual stream (active clients)
            </CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-dim border-b border-border">
                  <th className="pb-2 pr-4 font-medium">Client</th>
                  <th className="pb-2 pr-4 font-medium">Plan</th>
                  <th className="pb-2 pr-4 font-medium text-right">MRR</th>
                  <th className="pb-2 font-medium text-right">Est. monthly</th>
                </tr>
              </thead>
              <tbody>
                {activeClients.slice(0, 12).map((cl) => {
                  const name = cl.prospect?.company_name ?? "Client";
                  const est = calculateResidualCommission(userRole, cl.mrr);
                  return (
                    <tr key={cl.id} className="border-b border-border/60">
                      <td className="py-2 pr-4 text-text-primary">{name}</td>
                      <td className="py-2 pr-4 text-text-secondary capitalize">{cl.plan}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{formatCurrency(cl.mrr)}</td>
                      <td className="py-2 text-right tabular-nums text-accent-light">{formatCurrency(est)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {activeClients.length > 12 && (
              <p className="text-xs text-text-dim mt-2">Showing 12 of {activeClients.length} clients.</p>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Pie chart breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-accent-light" />
              Commission Breakdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }}
                    formatter={(v: number) => [formatCurrency(v), ""]}
                  />
                  <Legend iconType="circle" />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[200px] text-text-dim text-sm">
                No earnings this month
              </div>
            )}
          </CardContent>
        </Card>

        {/* Bonus progress */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-yellow" />
              Bonus Progress
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {bonusTier.nextTier ? (
              <>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs text-text-secondary">
                      {bonusTier.closesNeeded} closes to {formatCurrency(bonusTier.nextTier.bonus)} bonus
                    </span>
                    <span className="text-xs font-medium text-text-primary">{bonusTier.nextTier.closes} target</span>
                  </div>
                  <div className="h-2 bg-surface-3 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-yellow rounded-full transition-all"
                      style={{ width: `${bonusTier.progress}%` }}
                    />
                  </div>
                </div>
                <p className="text-xs text-text-dim">
                  Close {bonusTier.closesNeeded} more deal{bonusTier.closesNeeded !== 1 ? "s" : ""} this month to earn
                  your next bonus.
                </p>
              </>
            ) : (
              <div className="text-center py-4">
                <p className="text-sm font-semibold text-yellow">Max bonus tier reached! 🏆</p>
              </div>
            )}

            {/* Clawback tracker */}
            {clawbackRows.length > 0 && (
              <div className="mt-2 pt-3 border-t border-border">
                <div className="flex items-center gap-2 mb-2">
                  <Clock className="w-3.5 h-3.5 text-yellow" />
                  <span className="text-xs font-medium text-text-secondary">Clawback window</span>
                </div>
                {clawbackRows.slice(0, 5).map((c) => {
                  const days = clawbackDaysForCommission(c);
                  const label = c.client?.prospect?.company_name ?? formatCurrency(c.amount);
                  return (
                    <div key={c.id} className="flex items-center justify-between text-xs mb-1.5 gap-2">
                      <span className="text-text-dim truncate">{label}</span>
                      <span
                        className={cn(
                          "font-medium flex-shrink-0",
                          days < 14 ? "text-red" : days < 30 ? "text-yellow" : "text-green"
                        )}
                      >
                        {days}d left
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 12-month history */}
      <Card>
        <CardHeader>
          <CardTitle>Earnings history (12 months)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={historyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" />
              <XAxis dataKey="month" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#5C5876", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => `$${v}`}
              />
              <Tooltip
                contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }}
                formatter={(v: number) => [formatCurrency(v), "Earned"]}
              />
              <Bar dataKey="earned" fill="#7B5CF5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
