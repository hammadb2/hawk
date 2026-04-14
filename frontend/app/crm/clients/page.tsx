"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { formatUsd } from "@/lib/crm/format";
import type { CrmClientRow } from "@/lib/crm/types";
import { cn } from "@/lib/utils";

function statusClass(s: string): string {
  if (s === "active") return "text-emerald-600";
  if (s === "past_due") return "text-amber-400";
  if (s === "churned") return "text-rose-400";
  return "text-slate-600";
}

export default function ClientsPage() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [rows, setRows] = useState<CrmClientRow[]>([]);
  const [repNames, setRepNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("clients")
      .select("id, prospect_id, company_name, domain, plan, mrr_cents, stripe_customer_id, closing_rep_id, status, close_date, created_at, monitored_domains")
      .order("close_date", { ascending: false });
    if (error) {
      toast.error(error.message);
      setRows([]);
      setLoading(false);
      return;
    }
    const list = (data ?? []) as CrmClientRow[];
    setRows(list);
    const ids = Array.from(new Set(list.map((r) => r.closing_rep_id).filter(Boolean) as string[]));
    if (ids.length === 0) {
      setRepNames({});
    } else {
      const { data: profs } = await supabase.from("profiles").select("id, full_name, email").in("id", ids);
      const map: Record<string, string> = {};
      for (const p of profs ?? []) {
        map[p.id] = p.full_name ?? p.email ?? p.id.slice(0, 8);
      }
      setRepNames(map);
    }
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Clients</h1>
          <p className="mt-1 text-sm text-slate-600">Accounts created when deals are marked closed won.</p>
        </div>
        <button
          type="button"
          className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          onClick={() => void load()}
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="py-16 text-center text-slate-600">Loading…</div>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-slate-200 bg-white shadow-sm px-4 py-10 text-center text-sm text-slate-600">
          No clients yet. Win a deal from the pipeline to create one.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
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
              {rows.map((c) => (
                <tr key={c.id} className="border-b border-slate-200/90 hover:bg-white shadow-sm">
                  <td className="px-3 py-2">
                    {c.prospect_id ? (
                      <Link href={`/crm/prospects/${c.prospect_id}`} className="font-medium text-emerald-600 hover:underline">
                        {c.company_name ?? "—"}
                      </Link>
                    ) : (
                      <span className="font-medium text-slate-900">{c.company_name ?? "—"}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{c.domain ?? "—"}</td>
                  <td className="px-3 py-2 capitalize text-slate-700">{c.plan ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-800">{formatUsd(c.mrr_cents)}</td>
                  <td className="px-3 py-2 text-slate-600">
                    {c.closing_rep_id ? (repNames[c.closing_rep_id] ?? c.closing_rep_id.slice(0, 8)) : "—"}
                  </td>
                  <td className={cn("px-3 py-2 font-medium", statusClass(c.status))}>{c.status}</td>
                  <td className="px-3 py-2 text-slate-600">{new Date(c.close_date).toLocaleDateString()}</td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/crm/clients/${c.id}/enterprise`}
                      className="text-emerald-600/90 hover:underline"
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
