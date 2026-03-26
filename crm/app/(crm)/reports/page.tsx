"use client";

import { useState } from "react";
import { BarChart3, Download, RefreshCw } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend
} from "recharts";
import { formatCurrency, downloadCSV } from "@/lib/utils";
import { toast } from "@/components/ui/toast";

export default function ReportsPage() {
  const [loading] = useState(false);

  const pipelineData = [
    { stage: "New", count: 42 },
    { stage: "Scanned", count: 28 },
    { stage: "Loom", count: 19 },
    { stage: "Replied", count: 14 },
    { stage: "Call Bkd", count: 9 },
    { stage: "Proposal", count: 6 },
    { stage: "Won", count: 14 },
    { stage: "Lost", count: 18 },
  ];

  const mrrData = [
    { month: "Oct", mrr: 8200 },
    { month: "Nov", mrr: 9100 },
    { month: "Dec", mrr: 10200 },
    { month: "Jan", mrr: 11400 },
    { month: "Feb", mrr: 12100 },
    { month: "Mar", mrr: 13800 },
  ];

  const sourceData = [
    { name: "Charlotte", value: 58, color: "#7B5CF5" },
    { name: "Manual", value: 24, color: "#60A5FA" },
    { name: "Inbound", value: 12, color: "#34D399" },
    { name: "Referral", value: 6, color: "#FBBF24" },
  ];

  const handleExport = (reportName: string) => {
    toast({ title: `${reportName} exported`, variant: "success" });
  };

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
          <TabsTrigger value="charlotte">Charlotte</TabsTrigger>
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
              <StatCard label="Total Prospects" value="136" trend={{ value: 12 }} />
              <StatCard label="Won This Month" value="14" trend={{ value: 8 }} />
              <StatCard label="Avg Win Rate" value="24%" trend={{ value: 2 }} />
              <StatCard label="Avg Days to Close" value="18d" />
            </div>
            <Card>
              <CardHeader>
                <CardTitle>Pipeline by Stage</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={pipelineData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" />
                    <XAxis dataKey="stage" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#7B5CF5" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="commission">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Commission Report — March 2026</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Commission Report")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Total Paid" value={formatCurrency(4158)} />
              <StatCard label="Total Pending" value={formatCurrency(2178)} accent />
              <StatCard label="Clawbacks" value={formatCurrency(297)} />
              <StatCard label="Net Commissions" value={formatCurrency(6039)} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="charlotte">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">Charlotte Report — This Week</h2>
              <Button variant="secondary" size="sm" onClick={() => handleExport("Charlotte Report")} className="gap-1.5 h-7 text-xs">
                <Download className="w-3 h-3" /> Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-4 gap-4">
              <StatCard label="Emails Sent" value="1,240" />
              <StatCard label="Open Rate" value="41.2%" trend={{ value: 3 }} />
              <StatCard label="Reply Rate" value="8.4%" trend={{ value: 1 }} accent />
              <StatCard label="Closes Attributed" value="7" />
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
              <StatCard label="Active Clients" value="31" trend={{ value: 3 }} />
              <StatCard label="High Churn Risk" value="3" />
              <StatCard label="Avg NPS" value="7.8" trend={{ value: 0 }} />
              <StatCard label="Churn Rate MTD" value="3.2%" />
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
              <StatCard label="Top Closer" value="Jordan K." />
              <StatCard label="Team Close Rate" value="22%" trend={{ value: 4 }} />
              <StatCard label="Total Closes" value="14" trend={{ value: 8 }} accent />
              <StatCard label="At Risk Reps" value="2" />
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
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={mrrData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" />
                    <XAxis dataKey="month" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                    <Tooltip contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }} formatter={(v: number) => [formatCurrency(v), "MRR"]} />
                    <Line type="monotone" dataKey="mrr" stroke="#7B5CF5" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
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
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <CardHeader><CardTitle>Closes by Source</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={sourceData} cx="50%" cy="50%" outerRadius={80} dataKey="value">
                        {sourceData.map((entry, i) => (
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
                {sourceData.map((s) => (
                  <StatCard key={s.name} label={s.name} value={`${s.value}%`} />
                ))}
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
