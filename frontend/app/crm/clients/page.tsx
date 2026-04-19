"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import toast from "react-hot-toast";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { formatUsd } from "@/lib/crm/format";
import type { CrmClientRow } from "@/lib/crm/types";
import { useClients, useProfiles, useProspectsRealtimeSubscription } from "@/lib/crm/hooks";
import { cn } from "@/lib/utils";
import {
  crmEmptyState,
  crmPageSubtitle,
  crmPageTitle,
  crmTableRow,
  crmTableThead,
  crmTableWrap,
} from "@/lib/crm/crm-surface";

function statusClass(s: string): string {
  if (s === "active") return "text-emerald-400";
  if (s === "past_due") return "text-amber-400";
  if (s === "churned") return "text-rose-400";
  return "text-slate-400";
}

function ClientsTableSkeleton() {
  return (
    <div className={crmTableWrap}>
      <table className="w-full min-w-[800px] text-left text-sm">
        <thead className="border-b border-crmBorder bg-crmSurface2">
          <tr>
            {Array.from({ length: 8 }).map((_, i) => (
              <th key={i} className="px-3 py-2">
                <div className="h-3 w-16 animate-pulse rounded bg-crmSurface" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 8 }).map((_, r) => (
            <tr key={r} className="border-b border-crmBorder">
              {Array.from({ length: 8 }).map((__, c) => (
                <td key={c} className="px-3 py-2">
                  <div className="h-4 w-full max-w-[120px] animate-pulse rounded bg-crmSurface2" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuthShellSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-40 animate-pulse rounded-lg bg-crmSurface" />
      <ClientsTableSkeleton />
    </div>
  );
}

export default function ClientsPage() {
  const { authReady, session, profile } = useCrmAuth();
  const { data: rows = [], isLoading, error, mutate } = useClients();
  const { data: profiles = [] } = useProfiles();

  useProspectsRealtimeSubscription(!!session);

  const repNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const p of profiles) {
      map[p.id] = p.full_name ?? p.email ?? p.id.slice(0, 8);
    }
    return map;
  }, [profiles]);

  useEffect(() => {
    if (error) toast.error((error as Error).message);
  }, [error]);

  if (!authReady || !session || !profile) {
    return (
      <div className="mx-auto max-w-6xl">
        <AuthShellSkeleton />
      </div>
    );
  }

  const showSkeleton = isLoading && rows.length === 0;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className={crmPageTitle}>Clients</h1>
          <p className={crmPageSubtitle}>Accounts created when deals are marked closed won.</p>
        </div>
        <button
          type="button"
          className="rounded-lg border border-[#1e1e2e] bg-[#111118] px-3 py-1.5 text-sm text-slate-300 hover:bg-[#1a1a24]"
          onClick={() => void mutate()}
        >
          Refresh
        </button>
      </div>

      {showSkeleton ? (
        <ClientsTableSkeleton />
      ) : rows.length === 0 ? (
        <p className={crmEmptyState}>No clients yet. Win a deal from the pipeline to create one.</p>
      ) : (
        <div className={crmTableWrap}>
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead className={crmTableThead}>
              <tr>
                <th className="px-3 py-2">Company</th>
                <th className="px-3 py-2">Domain</th>
                <th className="px-3 py-2">Plan</th>
                <th className="px-3 py-2">MRR</th>
                <th className="px-3 py-2">Closer</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Closed</th>
                <th className="px-3 py-2">Enterprise</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c: CrmClientRow) => (
                <tr key={c.id} className={crmTableRow}>
                  <td className="px-3 py-2">
                    {c.prospect_id ? (
                      <Link href={`/crm/prospects/${c.prospect_id}`} className="font-medium text-emerald-400 hover:underline">
                        {c.company_name ?? "—"}
                      </Link>
                    ) : (
                      <span className="font-medium text-white">{c.company_name ?? "—"}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-400">{c.domain ?? "—"}</td>
                  <td className="px-3 py-2 capitalize text-slate-300">{c.plan ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-200">{formatUsd(c.mrr_cents)}</td>
                  <td className="px-3 py-2 text-slate-400">
                    {c.closing_rep_id ? (repNames[c.closing_rep_id] ?? c.closing_rep_id.slice(0, 8)) : "—"}
                  </td>
                  <td className={cn("px-3 py-2 font-medium", statusClass(c.status))}>{c.status}</td>
                  <td className="px-3 py-2 text-slate-400">{new Date(c.close_date).toLocaleDateString()}</td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/crm/clients/${c.id}/enterprise`}
                      className="text-emerald-400/90 hover:underline"
                    >
                      {(c.monitored_domains?.length ?? 0) > 0
                        ? `${c.monitored_domains?.length} extra`
                        : "Add domains"}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
