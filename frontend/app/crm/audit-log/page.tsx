"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLiveEffect } from "@/lib/hooks/use-refresh-signal";
import Link from "next/link";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { CrmActivityRow } from "@/lib/crm/types";
import { activityColor, activityLabel } from "@/lib/crm/activity-types";
import { Button } from "@/components/ui/button";
import {
  crmEmptyState,
  crmFieldSurface,
  crmPageSubtitle,
  crmPageTitle,
  crmTableRow,
  crmTableThead,
  crmTableWrap,
} from "@/lib/crm/crm-surface";

type ActivityWithProspect = CrmActivityRow & {
  prospect_company?: string | null;
  prospect_domain?: string | null;
  author_name?: string | null;
};

export default function AuditLogPage() {
  const supabase = useMemo(() => createClient(), []);
  const { profile, authReady, session } = useCrmAuth();
  const [rows, setRows] = useState<ActivityWithProspect[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [activityTypes, setActivityTypes] = useState<string[]>([]);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const load = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    try {
      let query = supabase
        .from("activities")
        .select("*")
        .order("created_at", { ascending: false })
        .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1);

      if (typeFilter !== "all") {
        query = query.eq("type", typeFilter);
      }

      const { data, error } = await query;
      if (error) throw error;
      const activities = (data ?? []) as CrmActivityRow[];

      // Enrich with prospect and author names
      const prospectIds = Array.from(new Set(activities.map((a) => a.prospect_id).filter(Boolean))) as string[];
      const authorIds = Array.from(new Set(activities.map((a) => a.created_by).filter(Boolean))) as string[];

      const [prospectRes, authorRes] = await Promise.all([
        prospectIds.length > 0
          ? supabase.from("prospects").select("id, company_name, domain").in("id", prospectIds)
          : { data: [] },
        authorIds.length > 0
          ? supabase.from("profiles").select("id, full_name, email").in("id", authorIds)
          : { data: [] },
      ]);

      const prospectMap = new Map<string, { company_name: string | null; domain: string | null }>();
      for (const p of (prospectRes.data ?? []) as { id: string; company_name: string | null; domain: string | null }[]) {
        prospectMap.set(p.id, { company_name: p.company_name, domain: p.domain });
      }

      const authorMap = new Map<string, string>();
      for (const a of (authorRes.data ?? []) as { id: string; full_name: string | null; email: string | null }[]) {
        authorMap.set(a.id, a.full_name ?? a.email ?? a.id.slice(0, 8));
      }

      const enriched: ActivityWithProspect[] = activities.map((a) => ({
        ...a,
        prospect_company: a.prospect_id ? prospectMap.get(a.prospect_id)?.company_name : null,
        prospect_domain: a.prospect_id ? prospectMap.get(a.prospect_id)?.domain : null,
        author_name: a.created_by ? authorMap.get(a.created_by) : null,
      }));

      setRows(enriched);

      // Load unique activity types for filter
      if (activityTypes.length === 0) {
        const types = Array.from(new Set(activities.map((a) => a.type))).sort();
        if (types.length > 0) setActivityTypes(types);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load audit log");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [profile, supabase, typeFilter, page, activityTypes.length]);

  useLiveEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#1e1e2e] border-t-emerald-500" />
      </div>
    );
  }

  const isCeoOrHos = profile.role === "ceo" || profile.role === "hos";
  if (!isCeoOrHos) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <h1 className={crmPageTitle}>Audit log</h1>
        <p className="text-sm text-slate-400">Only CEO and HoS can view the full audit log.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <h1 className={crmPageTitle}>Audit log</h1>
        <p className={crmPageSubtitle}>All CRM activity across prospects, ordered by most recent.</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          className={`rounded-lg px-3 py-1.5 text-sm ${crmFieldSurface}`}
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(0);
          }}
        >
          <option value="all">All activity types</option>
          {activityTypes.map((t) => (
            <option key={t} value={t}>
              {activityLabel(t)}
            </option>
          ))}
        </select>
        <span className="text-xs text-slate-400">
          Page {page + 1} · Showing up to {PAGE_SIZE} entries
        </span>
      </div>

      {loading ? (
        <div className="py-12 text-center text-slate-400">Loading…</div>
      ) : rows.length === 0 ? (
        <p className={crmEmptyState}>No activity found.</p>
      ) : (
        <div className={crmTableWrap}>
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className={crmTableThead}>
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Prospect</th>
                <th className="px-3 py-2">By</th>
                <th className="px-3 py-2">Details</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={crmTableRow}>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs font-medium ${activityColor(r.type)}`}>{activityLabel(r.type)}</span>
                  </td>
                  <td className="px-3 py-2">
                    {r.prospect_id ? (
                      <Link href={`/crm/prospects/${r.prospect_id}`} className="text-emerald-400 hover:underline">
                        {r.prospect_company ?? r.prospect_domain ?? r.prospect_id.slice(0, 8)}
                      </Link>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-300">{r.author_name ?? "—"}</td>
                  <td className="max-w-[200px] truncate px-3 py-2 text-xs text-slate-400">
                    {r.notes ?? (r.metadata ? JSON.stringify(r.metadata) : "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex justify-between">
        <Button
          variant="outline"
          size="sm"
          className="border-[#1e1e2e] bg-[#111118] text-slate-200 hover:bg-[#1a1a24]"
          disabled={page === 0}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="border-[#1e1e2e] bg-[#111118] text-slate-200 hover:bg-[#1a1a24]"
          disabled={rows.length < PAGE_SIZE}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
