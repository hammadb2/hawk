"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { useCRM } from "@/components/crm/crm-provider";
import { crmDashboardApi } from "@/lib/crm-api";
import type { DashboardStats } from "@/lib/crm-types";

function cents(n: number) {
  return `$${(n / 100).toLocaleString("en-CA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white border border-surface-3 rounded-lg p-5">
      <p className="text-xs text-text-secondary uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-text-primary">{value}</p>
      {sub && <p className="text-xs text-text-secondary mt-1">{sub}</p>}
    </div>
  );
}

export default function CRMDashboardPage() {
  const { token } = useAuth();
  const { crmUser, hasFullVisibility } = useCRM();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    crmDashboardApi.getStats(token).then(setStats).catch((e) => setError(e.message));
  }, [token]);

  if (error) return <p className="text-red-500 text-sm">{error}</p>;
  if (!stats) return <p className="text-text-secondary text-sm">Loading…</p>;

  const displayName = [crmUser?.first_name, crmUser?.last_name].filter(Boolean).join(" ") || crmUser?.email || "";

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-1">
        {hasFullVisibility ? "Overview" : `Welcome, ${displayName}`}
      </h1>
      <p className="text-sm text-text-secondary mb-6">
        {new Date().toLocaleDateString("en-CA", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
      </p>

      {/* CEO/HoS top row */}
      {hasFullVisibility && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
          <StatCard
            label="Total MRR"
            value={cents(stats.total_mrr_cents ?? 0)}
            sub={`+${cents(stats.mrr_added_this_month_cents ?? 0)} this month`}
          />
          <StatCard label="Active Clients" value={String(stats.active_clients ?? 0)} />
          <StatCard
            label="Churn Risk"
            value={String(stats.churn_risk_count ?? 0)}
            sub="medium or high risk"
          />
          <StatCard label="Closes This Month" value={String(stats.closes_this_month)} />
          <StatCard label="Pipeline Value" value={cents(stats.pipeline_value_cents)} />
          <StatCard
            label="Charlotte Emails Today"
            value={String(stats.charlotte_emails_today ?? 0)}
          />
        </div>
      )}

      {/* Rep row */}
      {!hasFullVisibility && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <StatCard label="Closes This Month" value={String(stats.closes_this_month)} />
          <StatCard label="Commission (MTD)" value={cents(stats.commission_this_month_cents)} />
          <StatCard label="Residual Income" value={cents(stats.total_residual_cents)} sub="monthly recurring" />
          <StatCard label="Tasks Due Today" value={String(stats.tasks_due_today)} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white border border-surface-3 rounded-lg p-5">
          <h2 className="font-medium mb-3">Quick Links</h2>
          <div className="flex flex-col gap-2">
            <a href="/crm/pipeline" className="text-purple-600 text-sm hover:underline">→ View Pipeline</a>
            <a href="/crm/prospects" className="text-purple-600 text-sm hover:underline">→ Add Prospect</a>
            <a href="/crm/scoreboard" className="text-purple-600 text-sm hover:underline">→ Scoreboard</a>
            {hasFullVisibility && <a href="/crm/charlotte" className="text-purple-600 text-sm hover:underline">→ Charlotte Outreach</a>}
          </div>
        </div>
        <div className="bg-white border border-surface-3 rounded-lg p-5">
          <h2 className="font-medium mb-3">Pipeline Summary</h2>
          <div className="flex flex-col gap-1">
            <div className="flex justify-between text-sm">
              <span className="text-text-secondary">Total Prospects</span>
              <span className="font-medium">{stats.total_prospects}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-secondary">Open Pipeline Value</span>
              <span className="font-medium">{cents(stats.pipeline_value_cents)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-text-secondary">Tasks Due Today</span>
              <span className="font-medium">{stats.tasks_due_today}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
