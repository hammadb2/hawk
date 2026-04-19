"use client";

import { useMemo } from "react";
import { crmSurfaceCard } from "@/lib/crm/crm-surface";
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

/* ── Types ────────────────────────────────────────────────────────────── */

export interface ChartData {
  chart_type: string;
  title: string;
  data: Record<string, unknown>[];
  x_key: string;
  y_keys: string[];
  colors: string[];
  y_label?: string;
  change_pct?: number;
  rates?: Record<string, number>;
  at_risk_count?: number;
  total?: number;
}

/* ── Color palette ────────────────────────────────────────────────────── */

const PALETTE = [
  "#10b981", // emerald
  "#6366f1", // indigo
  "#f59e0b", // amber
  "#3b82f6", // blue
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
];

/* ── Shared tooltip style ─────────────────────────────────────────────── */

const tooltipStyle = {
  contentStyle: {
    background: "#1e293b",
    border: "none",
    borderRadius: "8px",
    fontSize: "12px",
    color: "#f8fafc",
  },
  itemStyle: { color: "#f8fafc" },
};

/* ── Sub-charts ───────────────────────────────────────────────────────── */

function PipelineFunnel({ chart }: { chart: ChartData }) {
  const stageColors = [
    "#94a3b8", "#6366f1", "#8b5cf6", "#3b82f6",
    "#10b981", "#f59e0b", "#22c55e", "#ef4444",
  ];
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chart.data} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11, fill: "#64748b" }} />
        <YAxis dataKey={chart.x_key} type="category" width={80} tick={{ fontSize: 11, fill: "#64748b" }} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={28}>
          {chart.data.map((_, i) => (
            <Cell key={i} fill={stageColors[i % stageColors.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function RevenueTrend({ chart }: { chart: ChartData }) {
  const color = chart.colors[0] || PALETTE[1];
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chart.data} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
        <defs>
          <linearGradient id="mrrGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey={chart.x_key} tick={{ fontSize: 11, fill: "#64748b" }} />
        <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
        <Tooltip {...tooltipStyle} formatter={(v) => [`$${Number(v).toLocaleString()}`, chart.y_label || "MRR"]} />
        <Area
          type="monotone"
          dataKey="mrr"
          stroke={color}
          fill="url(#mrrGradient)"
          strokeWidth={2}
          dot={{ r: 3, fill: color }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function ComparePeriods({ chart }: { chart: ChartData }) {
  const colors = [PALETTE[1], PALETTE[0]];
  return (
    <div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={chart.data} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey={chart.x_key} tick={{ fontSize: 11, fill: "#64748b" }} />
          <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
          <Tooltip {...tooltipStyle} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={60}>
            {chart.data.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {chart.change_pct !== undefined && (
        <p className="mt-1 text-center text-xs text-slate-500">
          Change:{" "}
          <span className={chart.change_pct >= 0 ? "text-emerald-600 font-medium" : "text-rose-600 font-medium"}>
            {chart.change_pct >= 0 ? "+" : ""}
            {chart.change_pct}%
          </span>
        </p>
      )}
    </div>
  );
}

function CampaignHealth({ chart }: { chart: ChartData }) {
  const metricColors = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444"];
  const rates = chart.rates || {};
  return (
    <div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chart.data} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey={chart.x_key} tick={{ fontSize: 11, fill: "#64748b" }} />
          <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
          <Tooltip {...tooltipStyle} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
            {chart.data.map((_, i) => (
              <Cell key={i} fill={metricColors[i % metricColors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {Object.keys(rates).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
          {Object.entries(rates).map(([k, v]) => (
            <span key={k}>
              <span className="font-medium capitalize">{k.replace("_", " ")}:</span> {v}%
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function VaLeaderboard({ chart }: { chart: ChartData }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, chart.data.length * 32)}>
      <BarChart data={chart.data} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: "#64748b" }} />
        <YAxis dataKey={chart.x_key} type="category" width={80} tick={{ fontSize: 11, fill: "#64748b" }} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey="score" radius={[0, 4, 4, 0]} maxBarSize={24}>
          {chart.data.map((entry, i) => {
            const score = (entry as Record<string, unknown>).score as number;
            const fill = score >= 80 ? "#10b981" : score >= 50 ? "#f59e0b" : "#ef4444";
            return <Cell key={i} fill={fill} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function HealthDistribution({ chart }: { chart: ChartData }) {
  const rangeColors = ["#ef4444", "#f59e0b", "#eab308", "#10b981", "#059669"];
  return (
    <div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chart.data} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey={chart.x_key} tick={{ fontSize: 11, fill: "#64748b" }} />
          <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
          <Tooltip {...tooltipStyle} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
            {chart.data.map((_, i) => (
              <Cell key={i} fill={rangeColors[i % rangeColors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {chart.at_risk_count !== undefined && (
        <p className="mt-1 text-center text-xs text-slate-500">
          {chart.at_risk_count} of {chart.total} clients at risk (score &lt; 50)
        </p>
      )}
    </div>
  );
}

function GenericBar({ chart }: { chart: ChartData }) {
  const color = chart.colors[0] || PALETTE[0];
  const yKey = chart.y_keys[0] || "value";
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={chart.data} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey={chart.x_key} tick={{ fontSize: 11, fill: "#64748b" }} />
        <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey={yKey} fill={color} radius={[4, 4, 0, 0]} maxBarSize={48} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ── Main component ───────────────────────────────────────────────────── */

export function InlineChart({ data }: { data: ChartData }) {
  const ChartComponent = useMemo(() => {
    switch (data.chart_type) {
      case "pipeline_funnel":
        return PipelineFunnel;
      case "revenue_trend":
        return RevenueTrend;
      case "compare_periods":
        return ComparePeriods;
      case "campaign_health":
        return CampaignHealth;
      case "va_leaderboard":
        return VaLeaderboard;
      case "client_health_distribution":
        return HealthDistribution;
      default:
        return GenericBar;
    }
  }, [data.chart_type]);

  return (
    <div className={`mt-3 p-3 ${crmSurfaceCard}`}>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {data.title}
      </p>
      <ChartComponent chart={data} />
    </div>
  );
}
