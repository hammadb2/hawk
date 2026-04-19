"use client";

import { useState } from "react";
import Link from "next/link";
import type { Prospect, ProspectPipelineStatus } from "@/lib/crm/types";
import { PIPELINE_STATUS_LABELS, STAGE_META } from "@/lib/crm/types";
import { useProspectsList, useProspectsRealtimeSubscription } from "@/lib/crm/hooks";

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

function ProspectsTableSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-10 w-full animate-pulse rounded-lg bg-slate-100" />
      ))}
    </div>
  );
}

export default function ProspectsListPage() {
  const [pipelineFilter, setPipelineFilter] = useState<PipelineFilterValue>("all");
  const { data: rows = [], isLoading } = useProspectsList(pipelineFilter);

  useProspectsRealtimeSubscription(true);

  const showSkeleton = isLoading && rows.length === 0;

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
      {showSkeleton ? (
        <ProspectsTableSkeleton />
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
              {rows.map((p: Prospect) => (
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
