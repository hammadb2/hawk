"use client";

import { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { AlertTriangle, Bot, TrendingUp, Users, Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import { formatCurrency, formatRelativeTime, stageLabel, cn } from "@/lib/utils";
import type { Prospect } from "@/types/crm";

const MOCK_MRR_HISTORY = [
  { month: "Oct", gross: 8200, net: 7800 },
  { month: "Nov", gross: 9100, net: 8600 },
  { month: "Dec", gross: 10200, net: 9500 },
  { month: "Jan", gross: 11400, net: 10800 },
  { month: "Feb", gross: 12100, net: 11200 },
  { month: "Mar", gross: 13800, net: 12900 },
];

export function CEODashboard() {
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<"3M" | "6M" | "12M" | "All">("6M");
  const [feed, setFeed] = useState<Array<{
    id: string;
    type: string;
    text: string;
    time: string;
  }>>([]);

  useEffect(() => {
    setTimeout(() => {
      setFeed([
        { id: "1", type: "close", text: "Jordan closed Maple Tech on Shield — $199/mo", time: new Date(Date.now() - 300000).toISOString() },
        { id: "2", type: "prospect", text: "Charlotte created 12 new prospects from fintech.io campaign", time: new Date(Date.now() - 1200000).toISOString() },
        { id: "3", type: "reply", text: "Charlotte got a positive reply from canuck-solutions.ca", time: new Date(Date.now() - 2400000).toISOString() },
        { id: "4", type: "churn", text: "Churn risk HIGH flagged for GoldLeaf Corp (NPS: 4)", time: new Date(Date.now() - 3600000).toISOString() },
        { id: "5", type: "close", text: "Alex closed Northshore Dental on Starter — $99/mo", time: new Date(Date.now() - 5400000).toISOString() },
      ]);
      setLoading(false);
    }, 900);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">CEO Dashboard</h1>
        <p className="text-sm text-text-secondary mt-0.5">Full organization overview.</p>
      </div>

      {/* MRR Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard label="Current MRR" value={formatCurrency(13800)} trend={{ value: 14, label: "MoM" }} accent />
        <StatCard label="Net MRR" value={formatCurrency(12900)} trend={{ value: 7 }} />
        <StatCard label="MRR Added" value={formatCurrency(2800)} subValue="This month" trend={{ value: 24 }} />
        <StatCard label="MRR at Risk" value={formatCurrency(1100)} subValue="High churn" trend={{ value: -2 }} />
        <StatCard label="Active Clients" value="31" trend={{ value: 3 }} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Revenue Chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-accent-light" />
                Revenue Trend
              </CardTitle>
              <div className="flex items-center gap-1">
                {(["3M", "6M", "12M", "All"] as const).map((range) => (
                  <button
                    key={range}
                    onClick={() => setTimeRange(range)}
                    className={cn(
                      "px-2 py-0.5 rounded text-xs font-medium transition-colors",
                      timeRange === range
                        ? "bg-accent text-white"
                        : "text-text-dim hover:text-text-secondary"
                    )}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={MOCK_MRR_HISTORY}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F1C2E" />
                <XAxis dataKey="month" tick={{ fill: "#5C5876", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis
                  tick={{ fill: "#5C5876", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  contentStyle={{ background: "#0D0B14", border: "1px solid #1F1C2E", borderRadius: 8 }}
                  labelStyle={{ color: "#9B98B4" }}
                  formatter={(v: number) => [formatCurrency(v), ""]}
                />
                <Legend iconType="circle" />
                <Line type="monotone" dataKey="gross" stroke="#7B5CF5" strokeWidth={2} dot={false} name="Gross MRR" />
                <Line type="monotone" dataKey="net" stroke="#34D399" strokeWidth={2} dot={false} name="Net MRR" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Charlotte status */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-accent-light" />
              Charlotte
              <span className="ml-auto flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green realtime-dot" />
                <span className="text-xs text-green font-medium">Live</span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { label: "Emails Today", value: "248" },
              { label: "Open Rate", value: "42%" },
              { label: "Reply Rate", value: "8.1%" },
              { label: "Hot Leads", value: "7" },
              { label: "Closes Attributed", value: "3" },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">{label}</span>
                <span className="text-sm font-semibold text-text-primary">{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Today's Activity Feed */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue" />
              Live Activity Feed
              <span className="ml-auto flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green realtime-dot" />
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {feed.map((item) => (
              <div key={item.id} className="flex items-start gap-3 p-2.5 rounded-lg bg-surface-2">
                <div className={cn(
                  "w-2 h-2 rounded-full mt-1.5 flex-shrink-0",
                  item.type === "close" ? "bg-green" :
                  item.type === "churn" ? "bg-red" :
                  item.type === "reply" ? "bg-accent" : "bg-blue"
                )} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-text-primary leading-relaxed">{item.text}</p>
                  <p className="text-2xs text-text-dim mt-0.5">{formatRelativeTime(item.time)}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Churn Alerts */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red" />
              Churn Alerts
              <Badge variant="destructive" className="ml-auto">3 high risk</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              { company: "GoldLeaf Corp", mrr: 199, nps: 4, rep: "Jordan" },
              { company: "Apex Digital", mrr: 399, nps: 3, rep: "Alex" },
              { company: "Sigma Media", mrr: 99, nps: 5, rep: "Jordan" },
            ].map((client) => (
              <div
                key={client.company}
                className="flex items-center gap-3 p-3 rounded-lg border border-red/20 bg-red/5"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary">{client.company}</p>
                  <p className="text-xs text-text-dim">Rep: {client.rep} · NPS: {client.nps}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-sm font-semibold text-text-primary">{formatCurrency(client.mrr)}/mo</p>
                  <Badge variant="destructive" className="text-2xs">High Risk</Badge>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
