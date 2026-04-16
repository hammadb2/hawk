"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface DashboardData {
  revenue: {
    mrr: number;
    arr: number;
    active_clients: number;
    plan_breakdown: Record<string, number>;
  };
  pipeline: {
    total_prospects: number;
    new_this_week: number;
    stages: Record<string, number>;
    conversion_rate: number;
  };
  activity: {
    calls_today: number;
    emails_today: number;
    target_calls: number;
    call_attainment: number;
  };
  client_health: {
    average_score: number;
    at_risk_count: number;
    total_scored: number;
  };
  team: {
    active_vas: number;
    total_vas: number;
  };
  outbound: {
    recent_pipeline_runs: Array<Record<string, unknown>>;
    pending_replies: number;
  };
}

function KPICard({ label, value, sub, color = "emerald" }: { label: string; value: string | number; sub?: string; color?: string }) {
  const colorMap: Record<string, string> = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    red: "bg-red-50 text-red-700 border-red-200",
    slate: "bg-slate-50 text-slate-700 border-slate-200",
  };
  return (
    <div className={`rounded-xl border p-4 ${colorMap[color] || colorMap.emerald}`}>
      <p className="text-xs font-medium opacity-70">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      {sub && <p className="mt-0.5 text-xs opacity-60">{sub}</p>}
    </div>
  );
}

function StageBar({ stages }: { stages: Record<string, number> }) {
  const total = Object.values(stages).reduce((a, b) => a + b, 0) || 1;
  const colors: Record<string, string> = {
    new: "bg-blue-400",
    scanned: "bg-cyan-400",
    loom_sent: "bg-indigo-400",
    replied: "bg-yellow-400",
    call_booked: "bg-emerald-400",
    proposal_sent: "bg-orange-400",
    closed_won: "bg-green-500",
    lost: "bg-red-400",
  };

  return (
    <div className="space-y-2">
      <div className="flex h-4 overflow-hidden rounded-full">
        {Object.entries(stages).map(([stage, count]) => (
          <div
            key={stage}
            className={`${colors[stage] || "bg-slate-300"} transition-all`}
            style={{ width: `${(count / total) * 100}%` }}
            title={`${stage}: ${count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-3 text-xs">
        {Object.entries(stages).map(([stage, count]) => (
          <span key={stage} className="flex items-center gap-1">
            <span className={`inline-block h-2 w-2 rounded-full ${colors[stage] || "bg-slate-300"}`} />
            {stage.replace("_", " ")}: {count}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function CEODashboardPage() {
  const { profile, session } = useCrmAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [narration, setNarration] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchDashboard = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/dashboard`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      if (r.ok) {
        const resp = await r.json();
        if (resp.dashboard) {
          setData(resp.dashboard);
          setNarration(resp.narration || "");
        }
      } else {
        setError("Failed to load dashboard");
      }
    } catch {
      setError("Connection error");
    }
    setLoading(false);
  }, [session?.access_token]);

  useEffect(() => {
    void fetchDashboard();
  }, [fetchDashboard]);

  if (!profile) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (profile.role !== "ceo") {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-slate-500">God Mode Dashboard is CEO-only.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
          <p className="mt-3 text-sm text-slate-500">Loading God Mode Dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-red-500">{error}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">God Mode Dashboard</h1>
          <p className="text-sm text-slate-500">Real-time business intelligence by ARIA</p>
        </div>
        <button
          onClick={() => void fetchDashboard()}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 transition"
        >
          Refresh
        </button>
      </div>

      {/* AI Narration */}
      {narration && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white text-xs font-bold">
              A
            </div>
            <div className="prose prose-sm prose-slate max-w-none whitespace-pre-wrap text-sm text-slate-700">
              {narration}
            </div>
          </div>
        </div>
      )}

      {data && (
        <>
          {/* KPI Grid */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-6">
            <KPICard label="Monthly Revenue" value={`$${data.revenue.mrr.toLocaleString()}`} sub="MRR" color="emerald" />
            <KPICard label="Annual Run Rate" value={`$${data.revenue.arr.toLocaleString()}`} sub="ARR" color="emerald" />
            <KPICard label="Active Clients" value={data.revenue.active_clients} color="blue" />
            <KPICard
              label="Calls Today"
              value={`${data.activity.calls_today}/${data.activity.target_calls}`}
              sub={`${data.activity.call_attainment}% of target`}
              color={data.activity.call_attainment >= 80 ? "emerald" : data.activity.call_attainment >= 50 ? "amber" : "red"}
            />
            <KPICard
              label="Client Health"
              value={`${data.client_health.average_score}/100`}
              sub={`${data.client_health.at_risk_count} at risk`}
              color={data.client_health.at_risk_count > 0 ? "red" : "emerald"}
            />
            <KPICard label="Active VAs" value={`${data.team.active_vas}/${data.team.total_vas}`} color="blue" />
          </div>

          {/* Pipeline */}
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Pipeline ({data.pipeline.total_prospects} total)</h2>
            <StageBar stages={data.pipeline.stages} />
            <div className="mt-3 flex gap-6 text-xs text-slate-500">
              <span>New this week: {data.pipeline.new_this_week}</span>
              <span>Conversion rate: {data.pipeline.conversion_rate}%</span>
            </div>
          </div>

          {/* Plan Breakdown + Outbound */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 text-sm font-semibold text-slate-700">Revenue by Plan</h2>
              <div className="space-y-2">
                {Object.entries(data.revenue.plan_breakdown).map(([plan, count]) => (
                  <div key={plan} className="flex items-center justify-between">
                    <span className="text-sm capitalize text-slate-600">{plan}</span>
                    <span className="text-sm font-medium text-slate-900">{count} clients</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 text-sm font-semibold text-slate-700">Outbound Status</h2>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">Pending replies</span>
                  <span className="text-sm font-medium text-slate-900">{data.outbound.pending_replies}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">Recent pipeline runs</span>
                  <span className="text-sm font-medium text-slate-900">{data.outbound.recent_pipeline_runs.length}</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
