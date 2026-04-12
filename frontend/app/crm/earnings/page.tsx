"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { formatUsd } from "@/lib/crm/format";
import type { CrmCommissionRow, CrmRole } from "@/lib/crm/types";

type CommissionListRow = CrmCommissionRow & {
  clients: { company_name: string | null; domain: string | null } | null;
};

function normalizeClientEmbed(
  c: { company_name: string | null; domain: string | null } | { company_name: string | null; domain: string | null }[] | null
): { company_name: string | null; domain: string | null } | null {
  if (!c) return null;
  if (Array.isArray(c)) return c[0] ?? null;
  return c;
}

function showCloserColumn(role: CrmRole | undefined): boolean {
  return role !== "sales_rep";
}

function isExecRole(role: CrmRole | undefined): boolean {
  return role === "ceo" || role === "hos";
}

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

export default function EarningsPage() {
  const supabase = createClient();
  const { authReady, session, profile } = useCrmAuth();
  const [rows, setRows] = useState<CommissionListRow[]>([]);
  const [repNames, setRepNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [bulkUpdating, setBulkUpdating] = useState(false);

  const load = useCallback(async () => {
    if (!session?.user?.id) return;
    setLoading(true);
    const { data, error } = await supabase
      .from("crm_commissions")
      .select("id, client_id, rep_id, basis_mrr_cents, amount_cents, rate, status, created_at, clients(company_name, domain)")
      .order("created_at", { ascending: false });
    if (error) {
      toast.error(error.message);
      setRows([]);
      setLoading(false);
      return;
    }
    const list: CommissionListRow[] = (data ?? []).map((row: unknown) => {
      const r = row as CrmCommissionRow & {
        clients: { company_name: string | null; domain: string | null } | { company_name: string | null; domain: string | null }[] | null;
      };
      return {
        ...r,
        clients: normalizeClientEmbed(r.clients),
      };
    });
    setRows(list);

    const ids = Array.from(new Set(list.map((r) => r.rep_id)));
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
  }, [session?.user?.id, supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  async function updateCommissionStatus(commissionId: string, newStatus: "pending" | "approved" | "paid") {
    if (!session?.access_token || !API_URL) return;
    setUpdating(commissionId);
    try {
      const res = await fetch(`${API_URL}/api/crm/commissions/${commissionId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) {
        const txt = await res.text();
        toast.error(txt || "Failed to update");
        return;
      }
      toast.success(`Commission marked as ${newStatus}`);
      void load();
    } catch {
      toast.error("Network error");
    } finally {
      setUpdating(null);
    }
  }

  async function bulkUpdate(targetStatus: "approved" | "paid") {
    if (!session?.access_token || !API_URL) return;
    const sourceLabel = targetStatus === "approved" ? "pending" : "approved";
    const count = rows.filter((r) => r.status === sourceLabel).length;
    if (count === 0) {
      toast.error(`No ${sourceLabel} commissions to update`);
      return;
    }
    setBulkUpdating(true);
    try {
      const res = await fetch(`${API_URL}/api/crm/commissions/bulk-update`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ status: targetStatus }),
      });
      if (!res.ok) {
        const txt = await res.text();
        toast.error(txt || "Bulk update failed");
        return;
      }
      const j = await res.json();
      toast.success(`${j.updated_count ?? count} commissions marked as ${targetStatus}`);
      void load();
    } catch {
      toast.error("Network error");
    } finally {
      setBulkUpdating(false);
    }
  }

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
      </div>
    );
  }

  const totalPending = rows.filter((r) => r.status === "pending").reduce((s, r) => s + r.amount_cents, 0);
  const totalApproved = rows.filter((r) => r.status === "approved").reduce((s, r) => s + r.amount_cents, 0);
  const totalPaid = rows.filter((r) => r.status === "paid").reduce((s, r) => s + r.amount_cents, 0);
  const closerCol = showCloserColumn(profile.role);
  const canManage = isExecRole(profile.role);
  const pendingCount = rows.filter((r) => r.status === "pending").length;
  const approvedCount = rows.filter((r) => r.status === "approved").length;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Earnings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Commissions are created automatically when a deal is marked closed won (30% of first-month MRR).
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Pending</div>
          <div className="mt-1 text-xl font-semibold text-amber-200">{formatUsd(totalPending)}</div>
          <div className="text-xs text-zinc-600">{pendingCount} record{pendingCount !== 1 ? "s" : ""}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Approved</div>
          <div className="mt-1 text-xl font-semibold text-sky-300">{formatUsd(totalApproved)}</div>
          <div className="text-xs text-zinc-600">{approvedCount} record{approvedCount !== 1 ? "s" : ""}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Paid</div>
          <div className="mt-1 text-xl font-semibold text-emerald-300">{formatUsd(totalPaid)}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/80 px-4 py-3">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Records</div>
          <div className="mt-1 text-xl font-semibold text-zinc-200">{rows.length}</div>
        </div>
      </div>

      {canManage && (pendingCount > 0 || approvedCount > 0) && (
        <div className="flex flex-wrap gap-2">
          {pendingCount > 0 && (
            <button
              type="button"
              disabled={bulkUpdating}
              className="rounded-md border border-sky-700 bg-sky-900/40 px-4 py-2 text-sm font-medium text-sky-300 hover:bg-sky-800/60 disabled:opacity-50"
              onClick={() => void bulkUpdate("approved")}
            >
              {bulkUpdating ? "Updating…" : `Approve all pending (${pendingCount})`}
            </button>
          )}
          {approvedCount > 0 && (
            <button
              type="button"
              disabled={bulkUpdating}
              className="rounded-md border border-emerald-700 bg-emerald-900/40 px-4 py-2 text-sm font-medium text-emerald-300 hover:bg-emerald-800/60 disabled:opacity-50"
              onClick={() => void bulkUpdate("paid")}
            >
              {bulkUpdating ? "Updating…" : `Mark all approved as paid (${approvedCount})`}
            </button>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12 text-zinc-500">Loading…</div>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-8 text-center text-sm text-zinc-500">
          No commissions yet. Close a deal from the pipeline to create a client and commission row.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Client</th>
                {closerCol && <th className="px-3 py-2">Closer</th>}
                <th className="px-3 py-2">MRR</th>
                <th className="px-3 py-2">Commission</th>
                <th className="px-3 py-2">Status</th>
                {canManage && <th className="px-3 py-2">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-zinc-800/80 hover:bg-zinc-900/40">
                  <td className="px-3 py-2 text-zinc-400">{new Date(r.created_at).toLocaleDateString()}</td>
                  <td className="px-3 py-2 text-zinc-100">
                    {r.clients?.company_name ?? r.clients?.domain ?? "—"}
                    {r.clients?.domain && (
                      <span className="ml-1 text-xs text-zinc-500">({r.clients.domain})</span>
                    )}
                  </td>
                  {closerCol && <td className="px-3 py-2 text-zinc-300">{repNames[r.rep_id] ?? r.rep_id.slice(0, 8)}</td>}
                  <td className="px-3 py-2 text-zinc-300">{formatUsd(r.basis_mrr_cents)}</td>
                  <td className="px-3 py-2 font-medium text-emerald-400/90">{formatUsd(r.amount_cents)}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        r.status === "paid"
                          ? "text-emerald-400"
                          : r.status === "approved"
                            ? "text-sky-400"
                            : "text-amber-400"
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                  {canManage && (
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        {r.status === "pending" && (
                          <button
                            type="button"
                            disabled={updating === r.id}
                            className="rounded border border-sky-700 bg-sky-900/30 px-2 py-0.5 text-xs text-sky-300 hover:bg-sky-800/50 disabled:opacity-50"
                            onClick={() => void updateCommissionStatus(r.id, "approved")}
                          >
                            {updating === r.id ? "…" : "Approve"}
                          </button>
                        )}
                        {(r.status === "pending" || r.status === "approved") && (
                          <button
                            type="button"
                            disabled={updating === r.id}
                            className="rounded border border-emerald-700 bg-emerald-900/30 px-2 py-0.5 text-xs text-emerald-300 hover:bg-emerald-800/50 disabled:opacity-50"
                            onClick={() => void updateCommissionStatus(r.id, "paid")}
                          >
                            {updating === r.id ? "…" : "Mark paid"}
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
