"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { formatUsd } from "@/lib/crm/format";
import { crmEmptyState, crmPageSubtitle, crmPageTitle, crmTableRow, crmTableThead, crmTableWrap } from "@/lib/crm/crm-surface";

type GuaranteeClient = {
  id: string;
  company_name: string | null;
  domain: string | null;
  mrr_cents: number;
  status: string;
  guarantee_status: string | null;
  close_date: string;
  onboarded_at: string | null;
};

function guaranteeVariant(status: string | null): "green" | "amber" | "red" | "zinc" {
  switch (status) {
    case "active": return "green";
    case "at_risk": return "amber";
    case "breached": return "red";
    default: return "zinc";
  }
}

function guaranteeLabel(status: string | null): string {
  switch (status) {
    case "active": return "Active";
    case "at_risk": return "At Risk";
    case "breached": return "Breached";
    case "expired": return "Expired";
    default: return "Pending";
  }
}

function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

export default function GuaranteesPage() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [clients, setClients] = useState<GuaranteeClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "active" | "at_risk" | "breached" | "pending">("all");

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("clients")
      .select("id, company_name, domain, mrr_cents, status, guarantee_status, close_date, onboarded_at")
      .order("close_date", { ascending: false });
    if (error) {
      toast.error(error.message);
      setClients([]);
    } else {
      setClients((data ?? []) as GuaranteeClient[]);
    }
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  const filtered = filter === "all"
    ? clients
    : filter === "pending"
      ? clients.filter((c) => !c.guarantee_status)
      : clients.filter((c) => c.guarantee_status === filter);

  const counts = {
    all: clients.length,
    active: clients.filter((c) => c.guarantee_status === "active").length,
    at_risk: clients.filter((c) => c.guarantee_status === "at_risk").length,
    breached: clients.filter((c) => c.guarantee_status === "breached").length,
    pending: clients.filter((c) => !c.guarantee_status).length,
  };

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className={crmPageTitle}>Readiness Guarantees</h1>
        <p className={crmPageSubtitle}>
          Track guarantee status across all clients. At-risk clients need attention before SLA breach.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-3 sm:grid-cols-5">
        {(["all", "active", "at_risk", "breached", "pending"] as const).map((key) => {
          const colors = {
            all: "text-white",
            active: "text-emerald-400",
            at_risk: "text-amber-400",
            breached: "text-rose-400",
            pending: "text-slate-400",
          };
          const labels = { all: "Total", active: "Active", at_risk: "At Risk", breached: "Breached", pending: "Pending" };
          return (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`rounded-xl border px-4 py-3 text-left transition ${filter === key ? "border-emerald-500/40 bg-emerald-500/15" : "border-[#1e1e2e] bg-[#111118] hover:border-[#2a2a3e]"}`}
            >
              <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{labels[key]}</div>
              <div className={`mt-1 text-xl font-semibold ${colors[key]}`}>{counts[key]}</div>
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="flex justify-center py-12 text-slate-600">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
        </div>
      ) : filtered.length === 0 ? (
        <p className={crmEmptyState}>
          No clients match this filter.
        </p>
      ) : (
        <div className={crmTableWrap}>
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className={crmTableThead}>
              <tr>
                <th className="px-3 py-2">Company</th>
                <th className="px-3 py-2">Domain</th>
                <th className="px-3 py-2">MRR</th>
                <th className="px-3 py-2">Guarantee</th>
                <th className="px-3 py-2">Days since close</th>
                <th className="px-3 py-2">Onboarded</th>
                <th className="px-3 py-2">Account</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => {
                const v = guaranteeVariant(c.guarantee_status);
                const badgeColors = {
                  green: "bg-emerald-500/15 text-emerald-300 border-emerald-600/50",
                  amber: "bg-amber-900/50 text-amber-400 border-amber-700",
                  red: "bg-rose-900/50 text-rose-400 border-rose-700",
                  zinc: "bg-[#1a1a24] text-slate-400 border-[#1e1e2e]",
                };
                const days = daysSince(c.close_date);
                const daysColor = days > 90 ? "text-rose-400" : days > 60 ? "text-amber-400" : "text-slate-300";
                return (
                  <tr key={c.id} className={crmTableRow}>
                    <td className="px-3 py-2">
                      <Link href={`/crm/clients/${c.id}/onboarding`} className="font-medium text-emerald-600 hover:underline">
                        {c.company_name ?? "—"}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-slate-400">{c.domain ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-200">{formatUsd(c.mrr_cents)}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${badgeColors[v]}`}>
                        {guaranteeLabel(c.guarantee_status)}
                      </span>
                    </td>
                    <td className={`px-3 py-2 font-mono ${daysColor}`}>{days}d</td>
                    <td className="px-3 py-2 text-slate-600">
                      {c.onboarded_at ? new Date(c.onboarded_at).toLocaleDateString() : "Not yet"}
                    </td>
                    <td className="px-3 py-2">
                      <span className={c.status === "active" ? "text-emerald-600" : c.status === "churned" ? "text-rose-400" : "text-slate-600"}>
                        {c.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
