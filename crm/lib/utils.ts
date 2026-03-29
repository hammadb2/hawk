import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { PipelineStage, UserRole, ChurnRisk } from "@/types/crm";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(
  amount: number,
  currency: string = "CAD"
): string {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(d);
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

export function formatRelativeTime(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return "just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return formatDate(d);
}

export function getInitials(name: string): string {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function stageColor(stage: PipelineStage): string {
  const colors: Record<PipelineStage, string> = {
    new: "text-text-secondary border-text-dim",
    scanned: "text-blue border-blue/50",
    loom_sent: "text-accent-light border-accent/50",
    replied: "text-[#2DD4BF] border-[#2DD4BF]/50",
    call_booked: "text-yellow border-yellow/50",
    proposal_sent: "text-orange border-orange/50",
    closed_won: "text-green border-green/50",
    lost: "text-red border-red/50",
  };
  return colors[stage] ?? "text-text-secondary border-text-dim";
}

export function stageBgColor(stage: PipelineStage): string {
  const colors: Record<PipelineStage, string> = {
    new: "bg-surface-3 text-text-secondary",
    scanned: "bg-blue/10 text-blue",
    loom_sent: "bg-accent/10 text-accent-light",
    replied: "bg-[#2DD4BF]/10 text-[#2DD4BF]",
    call_booked: "bg-yellow/10 text-yellow",
    proposal_sent: "bg-orange/10 text-orange",
    closed_won: "bg-green/10 text-green",
    lost: "bg-red/10 text-red",
  };
  return colors[stage] ?? "bg-surface-3 text-text-secondary";
}

export function stageLabel(stage: PipelineStage): string {
  const labels: Record<PipelineStage, string> = {
    new: "New",
    scanned: "Scanned",
    loom_sent: "Loom Sent",
    replied: "Replied",
    call_booked: "Call Booked",
    proposal_sent: "Proposal Sent",
    closed_won: "Closed Won",
    lost: "Lost",
  };
  return labels[stage] ?? stage;
}

export function roleLabel(role: UserRole): string {
  const labels: Record<UserRole, string> = {
    ceo: "CEO",
    hos: "Head of Sales",
    team_lead: "Team Lead",
    rep: "Sales Rep",
    csm: "CSM",
  };
  return labels[role] ?? role;
}

export function roleShortLabel(role: UserRole): string {
  const labels: Record<UserRole, string> = {
    ceo: "CEO",
    hos: "HoS",
    team_lead: "TL",
    rep: "Rep",
    csm: "CSM",
  };
  return labels[role] ?? role;
}

export function churnRiskColor(risk: ChurnRisk): string {
  const colors: Record<ChurnRisk, string> = {
    low: "text-green bg-green/10",
    medium: "text-yellow bg-yellow/10",
    high: "text-red bg-red/10",
    critical: "text-red bg-red/20",
  };
  return colors[risk] ?? "text-text-secondary bg-surface-3";
}

export function hawkScoreColor(score: number): string {
  if (score >= 70) return "#F87171"; // red — high risk
  if (score >= 40) return "#FBBF24"; // amber — medium risk
  return "#34D399"; // green — low risk
}

export function hawkScoreLabel(score: number): string {
  if (score >= 70) return "High Risk";
  if (score >= 40) return "Medium Risk";
  return "Low Risk";
}

export function daysSince(date: string | Date): number {
  const d = typeof date === "string" ? new Date(date) : date;
  const now = new Date();
  return Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
}

export function daysUntil(date: string | Date): number {
  const d = typeof date === "string" ? new Date(date) : date;
  const now = new Date();
  return Math.floor((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

export function agingBorderColor(lastActivityAt: string): string {
  const days = daysSince(lastActivityAt);
  if (days >= 14) return "border-red/60";
  if (days >= 7) return "border-yellow/60";
  return "border-transparent";
}

export function planMRR(plan: string): number {
  const values: Record<string, number> = {
    starter: 99,
    shield: 199,
    enterprise: 399,
  };
  return values[plan] ?? 0;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return `${str.slice(0, maxLength)}...`;
}

export function downloadCSV(data: Record<string, unknown>[], filename: string) {
  if (data.length === 0) return;
  const headers = Object.keys(data[0]);
  const rows = data.map((row) =>
    headers
      .map((h) => {
        const val = row[h];
        const str = val === null || val === undefined ? "" : String(val);
        return str.includes(",") ? `"${str}"` : str;
      })
      .join(",")
  );
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Reject if promise does not settle within `ms` (clears spinner / hung Supabase fetches). */
export function withTimeout<T>(promise: Promise<T>, ms: number, label = "Request"): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
    promise.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      }
    );
  });
}
