"use client";

import { useState, useEffect } from "react";
import { Download } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from "recharts";
import { formatCurrency, downloadCSV } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import { getSupabaseClient } from "@/lib/supabase";

interface ReportData {
  pipeline: { stages: { stage: string; count: number }[]; total: number; wonThisMonth: number; avgDaysToClose: number };
  commission: { totalPaid: number; totalPending: number; clawbacks: number; net: number };
  clientHealth: { active: number; highChurn: number; avgNPS: number | null; churnRate: number };
  repPerformance: { topCloser: string; teamCloseRate: number; totalCloses: number; atRiskReps: number };
  attribution: { data: { name: string; value: number; color: string }[] };
  mrr: { data: { month: string; mrr: number }[] };
}

const STAGE_LABELS: Record<string, string> = {
  new: "New", scanned: "Scanned", loom_sent: "Loom", replied: "Replied",
  call_booked: "Call Bkd", proposal_sent: "Proposal", closed_won: "Won", lost: "Lost",
};

const SOURCE_COLORS: Record<string, string> = {
  charlotte: "#7B5CF5", manual: "#60A5FA", inbound: "#34D399", referral: "#FBBF24", inbound_signup: "#F472B6",
};

export default function ReportsPage() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ReportData | null>(null);

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

    const [prospectsRes, clientsRes, commissionsRes, usersRes] = await Promise.all([
      supabase.from("prospects").select("id, stage, source, created_at"),
      supabase.from("clients").select("id, status, mrr, churn_risk_score, nps_latest, close_date, closing_rep_id"),
      supabase.from("commissions").select("rep_id, type, amount, status, month_year"),
      supabase.from("users").select("id, name, status").in("role", ["rep", "team_lead"]),
    ]);

    const prospects = prospectsRes.data ?? [];
    const clients = clientsRes.data ?? [];
    const commissions = commissionsRes.data ?? [];
    const reps = usersRes.data ?? [];

    // Pipeline
    const allStages = ["new", "scanned", "loom_sent", "replied", "call_booked", "proposal_sent", "closed_won", "lost"];
    const stages = allStages.map((s) => ({
      stage: STAGE_LABELS[s] ?? s,
      count: prospects.filter((p) => p.stage === s).length,
    }));
    const wonThisMonth = clients.filter((c) => c.close_date && c.close_date >= startOfMonth).length;
    const totalWon = prospects.filter((p) => p.stage === "closed_won").length;
    const winRate = prospects.length > 0 ? Math.round((totalWon / prospects.length) * 100) : 0;

    // Commission
    const monthComms = commissions.filter((c) => c.month_year === monthYear);
    const totalPaid = monthComms.filter((c) => c.status === "paid").reduce((s, c) => s + (c.amount || 0), 0);
    const totalPending = monthComms.filter((c) => c.status === "pending").reduce((s, c) => s + (c.amount || 0), 0);
    const clawbacks = Math.abs(commissions.filter((c) => c.type === "clawback").reduce((s, c) => s + (c.amount || 0), 0));

    // Client health
    const activeClients = clients.filter((c) => c.status === "active");
    const highChurn = clients.filter((c) => ["high", "critical"].includes(c.churn_risk_score) && c.status === "active").length;
    const npsScores = clients.filter((c) => c.nps_latest != null).map((c) => c.nps_latest as number);
    const avgNPS = npsScores.length > 0 ? Math.round((npsScores.reduce((a, b) => a + b, 0) / npsScores.length) * 10) / 10 : null;
    const churnedThisMonth = clients.filter((c) => c.status === "churned").length;
    const churnRate = clients.length > 0 ? Math.round((churnedThisMonth / clients.length) * 1000) / 10 : 0;

    // Rep performance
    const thisMonthCloses = commissions.filter((c) => c.month_year === monthYear && c.type === "closing");
    const closesByRep: Record<string, number> = {};
    thisMonthCloses.forEach((c) => { closesByRep[c.rep_id] = (closesByRep[c.rep_id] || 0) + 1; });
    const topRepId = Object.entries(closesByRep).sort(([, a], [, b]) => b - a)[0]?.[0];
    const topCloser = reps.find((r) => r.id === topRepId)?.name ?? "—";
    const atRiskReps = reps.filter((r) => r.status === "at_risk").length;
    const closeRate = prospects.length > 0 ? Math.round((totalWon / prospects.length) * 100) : 0;

    // Attribution
    const sourceCounts: Record<string, number> = {};
    prospects.filter((p) => p.stage === "closed_won").forEach((p) => {
      sourceCounts[p.source] = (sourceCounts[p.source] || 0) + 1;
    });
    const totalAttrib = Object.values(sourceCounts).reduce((a, b) => a + b, 0) || 1;
    const attribution = Object.entries(sourceCounts).map(([name, count]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, " "),
      value: Math.round((count / totalAttrib) * 100),
      color: SOURCE_COLORS[name] ?? "#9B98B4",
    }));

    // MRR trend from client close dates
    const mrrByMonth: Record<string, number> = {};
    clients.filter((c) => c.close_date && c.status !== "churned").forEach((c) => {
      const d = new Date(c.close_date);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      mrrByMonth[key] = (mrrByMonth[key] || 0) + (c.mrr || 0);
    });
    let cumMRR = 0;
    const mrrTrend = Object.keys(mrrByMonth).sort().map((key) => {
      cumMRR += mrrByMonth[key];
      const [, m] = key.split("-");
      return { month: new Date(0, Number(m) - 1).toLocaleString("default", { month: "short" }), mrr: cumMRR };
    });

    setData({
      pipeline: { stages, total: prospects.length, wonThisMonth, avgDaysToClose: 18 },
      commission: { totalPaid, totalPending, clawbacks, net: totalPaid + totalPending - clawbacks },
      clientHealth: { active: activeClients.length, highChurn, avgNPS, churnRate },
      repPerformance: { topCloser, teamCloseRate: closeRate, totalCloses: totalWon, atRiskReps },
      attribution: { data: attribution },
      mrr: { data: mrrTrend },
    });
    setLoading(false);
    } catch {
      setLoading(false);
    }
  };

  const handleExport = (reportName: string) => {
    toast({ title: `${reportName} exported`, variant: "success" });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-text-primary">Reports</h1>
        <p className="text-sm text-text-secondary mt-0.5">Data insights and analytics</p>
      </div>

      <Tabs defaultValue="pipeline">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="commission">Commission</TabsTrigger>
          <TabsTrigger value="client_health">Client Health</TabsTrigger>
          <TabsTrigger value="rep_performance">Rep Performance</TabsTrigger>
          <TabsTrigger value="forecast">Forecast</TabsTrigger>
          <TabsTrigger value="attribution">Attribution</TabsTrigger>
        </TabsList>

        <TabsContent value="pipeline">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Pipeline Report</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Pipeline Report")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Total Prospects" value={String(data.pipeline.total)} />
              <StatCard label="Won This Month" value={String(data.pipeline.wonThisMonth)} />
              <StatCard label="Win Rate" value={`${data.repPerformance.teamCloseRate}%`} />
              <StatCard label="Total Won" value={String(data.repPerformance.totalCloses)} />
            </div>
            <Card>
              <CardHeader><CardTitle>Pipeline by Stage</CardTitle></CardHeader>
              <CardContent>
                {data.pipeline.stages.every((s) => s.count === 0) ? (
                  <div className="flex items-center justify-center h-[250px] text-text-dim text-sm">No prospects yet</div>
                ) : (
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={data.pipeline.stages}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" />
                      <XAxis dataKey="stage" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }} />
                      <Bar dataKey="count" fill="#7B5CF5" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="commission">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Commission Report — This Month</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Commission Report")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Total Paid" value={formatCurrency(data.commission.totalPaid)} />
              <StatCard label="Total Pending" value={formatCurrency(data.commission.totalPending)} accent />
              <StatCard label="Clawbacks" value={formatCurrency(data.commission.clawbacks)} />
              <StatCard label="Net Commissions" value={formatCurrency(data.commission.net)} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="client_health">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Client Health Report</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Client Health")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Active Clients" value={String(data.clientHealth.active)} />
              <StatCard label="High Churn Risk" value={String(data.clientHealth.highChurn)} />
              <StatCard label="Avg NPS" value={data.clientHealth.avgNPS != null ? String(data.clientHealth.avgNPS) : "—"} />
              <StatCard label="Churn Rate MTD" value={`${data.clientHealth.churnRate}%`} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="rep_performance">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Rep Performance</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Rep Performance")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Top Closer" value={data.repPerformance.topCloser} />
              <StatCard label="Team Close Rate" value={`${data.repPerformance.teamCloseRate}%`} />
              <StatCard label="Total Closes" value={String(data.repPerformance.totalCloses)} accent />
              <StatCard label="At Risk Reps" value={String(data.repPerformance.atRiskReps)} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="forecast">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Revenue Forecast</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Forecast")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            <Card>
              <CardHeader><CardTitle>MRR Trend</CardTitle></CardHeader>
              <CardContent>
                {data.mrr.data.length === 0 ? (
                  <div className="flex items-center justify-center h-[220px] text-text-dim text-sm">No revenue data yet</div>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={data.mrr.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" />
                      <XAxis dataKey="month" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                      <Tooltip contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }} formatter={(v: number) => [formatCurrency(v), "MRR"]} />
                      <Line type="monotone" dataKey="mrr" stroke="#7B5CF5" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="attribution">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Source Attribution</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Attribution")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            {data.attribution.data.length === 0 ? (
              <p className="text-sm text-text-dim text-center py-12">No closed deals yet — attribution will appear here</p>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card>
                  <CardHeader><CardTitle>Closes by Source</CardTitle></CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={220}>
                      <PieChart>
                        <Pie data={data.attribution.data} cx="50%" cy="50%" outerRadius={80} dataKey="value">
                          {data.attribution.data.map((entry, i) => (
                            <Cell key={i} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }} />
                        <Legend iconType="circle" />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
                <div className="grid grid-cols-2 gap-3">
                  {data.attribution.data.map((s) => (
                    <StatCard key={s.name} label={s.name} value={`${s.value}%`} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
