"use client";

import { useState } from "react";
import { RefreshCw, Activity, TrendingDown, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { ClientHealthSync, ChurnRisk } from "@/types/crm";
import { cn, formatRelativeTime, formatDate } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

interface HealthPanelProps {
  clientId: string;
  health: ClientHealthSync | null;
  onSync?: () => void;
}

const RISK_CONFIG: Record<ChurnRisk, { label: string; color: string; bg: string; border: string }> = {
  low:      { label: "Low",      color: "text-green-400",  bg: "bg-green-400/10",  border: "border-green-400/30" },
  medium:   { label: "Medium",   color: "text-yellow-400", bg: "bg-yellow-400/10", border: "border-yellow-400/30" },
  high:     { label: "High",     color: "text-orange-400", bg: "bg-orange-400/10", border: "border-orange-400/30" },
  critical: { label: "Critical", color: "text-red-400",    bg: "bg-red-400/10",    border: "border-red-500/50" },
};

function ChurnBadge({ label, numeric }: { label: ChurnRisk; numeric: number }) {
  const config = RISK_CONFIG[label] ?? RISK_CONFIG.low;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border cursor-default",
        config.color, config.bg, config.border,
      )}
      title={`Raw score: ${numeric}/100`}
    >
      {label === "critical" && <AlertTriangle className="w-3.5 h-3.5" />}
      {config.label}
      <span className="opacity-60 text-xs">({numeric})</span>
    </span>
  );
}

function StatBox({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-surface-2 rounded-lg p-3">
      <p className="text-xs text-text-dim mb-1">{label}</p>
      <p className="text-lg font-semibold text-text-primary">{value}</p>
      {sub && <p className="text-xs text-text-dim mt-0.5">{sub}</p>}
    </div>
  );
}

function FeatureChip({ name, accessed }: { name: string; accessed: boolean }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs",
      accessed ? "bg-accent/15 text-accent" : "bg-surface-3 text-text-dim line-through",
    )}>
      {accessed ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
      {name}
    </span>
  );
}

export function HealthPanel({ clientId, health, onSync }: HealthPanelProps) {
  const [syncing, setSyncing] = useState(false);

  async function handleSync() {
    setSyncing(true);
    try {
      await fetch(`${API_URL}/api/crm/sync/account/${clientId}`, { method: "POST" });
      // Slight delay so background task completes before parent re-fetches
      await new Promise((r) => setTimeout(r, 1500));
      onSync?.();
    } finally {
      setSyncing(false);
    }
  }

  if (!health) {
    return (
      <div className="rounded-xl border border-surface-3 bg-surface-1 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-text-primary flex items-center gap-2">
            <Activity className="w-4 h-4 text-accent" />
            Product Health
          </h3>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-1.5 text-xs text-text-dim hover:text-text-primary transition-colors"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", syncing && "animate-spin")} />
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
        <p className="text-sm text-text-dim">
          No sync data yet.{" "}
          {health === null && "This client has no linked HAWK account or has never been synced."}
        </p>
      </div>
    );
  }

  const riskConfig = RISK_CONFIG[health.churn_risk_label] ?? RISK_CONFIG.low;
  const features = Object.entries(health.features_accessed ?? {});
  const daysUntilRenewal = health.renewal_date
    ? Math.ceil((new Date(health.renewal_date).getTime() - Date.now()) / 86400000)
    : null;

  return (
    <div className={cn(
      "rounded-xl border bg-surface-1 p-6 space-y-5",
      health.churn_risk_label === "critical" ? "border-red-500/40" : "border-surface-3",
    )}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-text-primary flex items-center gap-2">
          <Activity className="w-4 h-4 text-accent" />
          Product Health
        </h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-text-dim">
            Synced {formatRelativeTime(health.synced_at)}
          </span>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-1.5 text-xs text-text-dim hover:text-text-primary transition-colors"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", syncing && "animate-spin")} />
            {syncing ? "Syncing…" : "Sync"}
          </button>
        </div>
      </div>

      {/* Churn Risk */}
      <div className={cn("flex items-center justify-between p-3 rounded-lg border", riskConfig.bg, riskConfig.border)}>
        <div className="flex items-center gap-2">
          <TrendingDown className={cn("w-4 h-4", riskConfig.color)} />
          <span className="text-sm font-medium text-text-primary">Churn Risk</span>
        </div>
        <ChurnBadge label={health.churn_risk_label} numeric={health.churn_risk_numeric} />
      </div>

      {/* Usage Stats */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <StatBox
          label="Scans this month"
          value={health.scans_this_month}
          sub={`${health.total_scans} total`}
        />
        <StatBox
          label="Last login"
          value={health.last_login_date ? formatRelativeTime(health.last_login_date) : "Never"}
        />
        <StatBox
          label="Sessions / mo"
          value={health.sessions_this_month}
          sub={`~${health.avg_session_minutes}min avg`}
        />
        <StatBox
          label="Onboarding"
          value={`${health.onboarding_pct}%`}
          sub={health.onboarding_pct < 50 ? "⚠ Below 50%" : ""}
        />
      </div>

      {/* Reports + NPS */}
      <div className="grid grid-cols-2 gap-2.5">
        <StatBox
          label="Reports"
          value={`${health.reports_downloaded} / ${health.reports_generated}`}
          sub="downloaded / generated"
        />
        <StatBox
          label="NPS"
          value={health.nps_score !== null ? health.nps_score : "—"}
          sub={health.nps_comment ? `"${health.nps_comment.slice(0, 40)}…"` : undefined}
        />
      </div>

      {/* Renewal + Billing */}
      {(daysUntilRenewal !== null || health.billing_status) && (
        <div className="flex items-center gap-4 text-sm">
          {daysUntilRenewal !== null && (
            <span className={cn(
              daysUntilRenewal <= 7 ? "text-orange-400 font-medium" : "text-text-secondary",
            )}>
              Renewal in {daysUntilRenewal}d — {formatDate(health.renewal_date!)}
            </span>
          )}
          {health.billing_status && health.billing_status !== "active" && (
            <span className="text-red-400 font-medium capitalize">{health.billing_status}</span>
          )}
          {health.payment_failed_count > 0 && (
            <span className="text-red-400">
              ⚠ {health.payment_failed_count} payment failure{health.payment_failed_count > 1 ? "s" : ""}
            </span>
          )}
        </div>
      )}

      {/* Alert flags */}
      {(health.cancellation_intent || health.downgrade_requested || health.upgrade_clicked) && (
        <div className="flex flex-wrap gap-2">
          {health.cancellation_intent && (
            <span className="px-2 py-0.5 rounded bg-red-500/15 border border-red-500/30 text-red-400 text-xs font-medium">
              🚨 Cancellation intent
            </span>
          )}
          {health.downgrade_requested && (
            <span className="px-2 py-0.5 rounded bg-orange-500/15 border border-orange-500/30 text-orange-400 text-xs font-medium">
              Downgrade requested
            </span>
          )}
          {health.upgrade_clicked && (
            <span className="px-2 py-0.5 rounded bg-accent/15 border border-accent/30 text-accent text-xs font-medium">
              Upgrade page viewed
            </span>
          )}
        </div>
      )}

      {/* Features */}
      {features.length > 0 && (
        <div>
          <p className="text-xs text-text-dim mb-2 uppercase tracking-wide">Feature Access</p>
          <div className="flex flex-wrap gap-1.5">
            {features.map(([name, accessed]) => (
              <FeatureChip key={name} name={name} accessed={accessed} />
            ))}
          </div>
        </div>
      )}

      {/* Domains */}
      {health.all_domains.length > 0 && (
        <div>
          <p className="text-xs text-text-dim mb-1 uppercase tracking-wide">Monitored Domains</p>
          <div className="flex flex-wrap gap-1.5">
            {health.all_domains.map((d) => (
              <span key={d} className="px-2 py-0.5 rounded bg-surface-2 text-text-secondary text-xs font-mono">{d}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
