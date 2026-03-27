"use client";

import { useState, useEffect } from "react";
import { DollarSign, Clock, TrendingUp, Download } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { commissionsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { formatCurrency, formatDate, downloadCSV, daysUntil, cn } from "@/lib/utils";
import { calculateMonthlyTotal, getNextBonusTier } from "@/lib/commission";
import type { Commission } from "@/types/crm";

const PIE_COLORS = {
  closing: "#7B5CF5",
  residual: "#34D399",
  bonus: "#FBBF24",
  override: "#60A5FA",
};

export function MyEarnings() {
  const [commissions, setCommissions] = useState<Commission[]>([]);
  const [loading, setLoading] = useState(false);
  const [monthYear] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const result = await commissionsApi.myEarnings(monthYear);
        if (result.success && result.data) {
          setCommissions(result.data);
        }
      } catch {
        toast({ title: "Failed to load earnings", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    load();
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

  // Build history from real commissions grouped by month_year
  const historyMap: Record<string, number> = {};
  commissions.forEach((c) => {
    historyMap[c.month_year] = (historyMap[c.month_year] || 0) + c.amount;
  });
  const historyData = Object.entries(historyMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-6)
    .map(([key, earned]) => {
      const [, m] = key.split("-");
      return { month: new Date(0, Number(m) - 1).toLocaleString("default", { month: "short" }), earned };
    });

  const handleExport = () => {
    downloadCSV(
      commissions.map((c) => ({
        type: c.type,
        amount: c.amount,
        status: c.status,
        month: c.month_year,
        calculated_at: c.calculated_at,
      })),
      `hawk-commissions-${monthYear}.csv`
    );
    toast({ title: "CSV exported", variant: "success" });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">My Earnings</h1>
          <p className="text-sm text-text-secondary">Commission breakdown for {monthYear}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={handleExport} className="gap-1.5">
          <Download className="w-3.5 h-3.5" />
          Export for Taxes
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Earned" value={formatCurrency(totals.net)} accent />
        <StatCard
          label="Status"
          value={
            totals.clawback > 0 ? "At Risk" :
            commissions.some((c) => c.status === "paid") ? "Paid" : "Pending"
          }
        />
        <StatCard label="Closing" value={formatCurrency(totals.closing)} />
        <StatCard label="Residual" value={formatCurrency(totals.residual)} />
      </div>

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
                  Close {bonusTier.closesNeeded} more deal{bonusTier.closesNeeded !== 1 ? "s" : ""} this month to earn your next bonus.
                </p>
              </>
            ) : (
              <div className="text-center py-4">
                <p className="text-sm font-semibold text-yellow">Max bonus tier reached! 🏆</p>
              </div>
            )}

            {/* Clawback tracker */}
            {commissions.some((c) => c.type === "closing" && c.status !== "paid") && (
              <div className="mt-2 pt-3 border-t border-border">
                <div className="flex items-center gap-2 mb-2">
                  <Clock className="w-3.5 h-3.5 text-yellow" />
                  <span className="text-xs font-medium text-text-secondary">Clawback Window</span>
                </div>
                {commissions
                  .filter((c) => c.type === "closing" && c.status === "pending")
                  .slice(0, 3)
                  .map((c) => {
                    const days = daysUntil(c.calculated_at);
                    return (
                      <div key={c.id} className="flex items-center justify-between text-xs mb-1">
                        <span className="text-text-dim">{formatCurrency(c.amount)} closing</span>
                        <span className={cn(
                          "font-medium",
                          days < 30 ? "text-red" : days < 60 ? "text-yellow" : "text-green"
                        )}>
                          {days}d remaining
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
          <CardTitle>Earnings History (12 months)</CardTitle>
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
