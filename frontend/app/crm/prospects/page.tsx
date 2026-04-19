"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import type { Prospect, ProspectPipelineStatus } from "@/lib/crm/types";
import { PIPELINE_STATUS_LABELS, STAGE_META } from "@/lib/crm/types";
import toast from "react-hot-toast";

type PipelineFilterValue = "all" | ProspectPipelineStatus | "active";

const PIPELINE_FILTER_OPTIONS: { value: PipelineFilterValue; label: string }[] = [
  { value: "all", label: "All prospects" },
  { value: "active", label: "Active pipeline (hide suppressed)" },
  ...(Object.keys(PIPELINE_STATUS_LABELS) as ProspectPipelineStatus[]).map((k) => ({
    value: k,
    label: PIPELINE_STATUS_LABELS[k],
  })),
];

function pipelineLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return PIPELINE_STATUS_LABELS[status as ProspectPipelineStatus] ?? status;
}

export default function ProspectsListPage() {
  const supabase = useMemo(() => createClient(), []);
  const [rows, setRows] = useState<Prospect[]>([]);
  const [loading, setLoading] = useState(true);
  const [pipelineFilter, setPipelineFilter] = useState<PipelineFilterValue>("all");

  const load = useCallback(
    async (opts?: { quiet?: boolean }) => {
      if (!opts?.quiet) setLoading(true);
      let q = supabase.from("prospects").select("*");
      if (pipelineFilter === "active") {
        q = q.or("pipeline_status.is.null,pipeline_status.neq.suppressed");
      } else if (pipelineFilter !== "all") {
        q = q.eq("pipeline_status", pipelineFilter);
      }
      const { data, error } = await q
        .order("lead_score", { ascending: false, nullsFirst: false })
        .order("created_at", { ascending: false });
      if (error) toast.error(error.message);
      setRows((data as Prospect[]) ?? []);
      if (!opts?.quiet) setLoading(false);
    },
    [supabase, pipelineFilter],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const channel = supabase
      .channel("prospects-list-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "prospects" }, () => {
        void load({ quiet: true });
      })
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [supabase, load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Prospects</h1>
          <p className="text-sm text-slate-600">
            All prospects you can access (RLS). Updates live as the ARIA pipeline writes to CRM.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="pipeline-filter" className="text-xs font-medium uppercase text-slate-500">
            Pipeline status
          </label>
          <select
            id="pipeline-filter"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm"
            value={pipelineFilter}
            onChange={(e) => setPipelineFilter(e.target.value as PipelineFilterValue)}
          >
            {PIPELINE_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      {loading ? (
        <div className="flex justify-center py-12 text-slate-600">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-100 text-xs uppercase text-slate-600">
              <tr>
                <th className="px-3 py-2">Company</th>
                <th className="px-3 py-2">Domain</th>
                <th className="px-3 py-2">Stage</th>
                <th className="px-3 py-2">Pipeline</th>
                <th className="px-3 py-2 text-right">Lead score</th>
                <th className="px-3 py-2 text-right">Hawk score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-b border-slate-200/90 shadow-sm hover:bg-white">
                  <td className="px-3 py-2">
                    <Link href={`/crm/prospects/${p.id}`} className="font-medium text-emerald-600 hover:underline">
                      {p.company_name ?? p.domain}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{p.domain}</td>
                  <td className="px-3 py-2">{STAGE_META[p.stage]?.label ?? p.stage}</td>
                  <td className="px-3 py-2 text-slate-700">{pipelineLabel(p.pipeline_status ?? undefined)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                    {p.lead_score != null ? p.lead_score : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">{p.hawk_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
