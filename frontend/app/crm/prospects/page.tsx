"use client";

import { useState } from "react";
import Link from "next/link";
import type { Prospect, ProspectPipelineStatus } from "@/lib/crm/types";
import { PIPELINE_STATUS_LABELS, STAGE_META } from "@/lib/crm/types";
import { useProspectsList, useProspectsRealtimeSubscription } from "@/lib/crm/hooks";
import { crmPageSubtitle, crmPageTitle, crmTableRow, crmTableThead, crmTableWrap } from "@/lib/crm/crm-surface";

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
    <div className={crmTableWrap}>
      <table className="w-full min-w-[880px] text-left text-sm">
        <thead className="border-b border-crmBorder bg-crmSurface2">
          <tr>
            {["Company", "Domain", "Stage", "Pipeline", "Lead", "Hawk"].map((label) => (
              <th key={label} className="px-3 py-2">
                <div className="h-3 w-20 animate-pulse rounded bg-crmSurface" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 8 }).map((_, r) => (
            <tr key={r} className="border-b border-crmBorder">
              <td className="px-3 py-2">
                <div className="h-4 w-40 animate-pulse rounded bg-crmSurface2" />
              </td>
              <td className="px-3 py-2">
                <div className="h-4 w-32 animate-pulse rounded bg-crmSurface2" />
              </td>
              <td className="px-3 py-2">
                <div className="h-4 w-24 animate-pulse rounded bg-crmSurface2" />
              </td>
              <td className="px-3 py-2">
                <div className="h-4 w-28 animate-pulse rounded bg-crmSurface2" />
              </td>
              <td className="px-3 py-2 text-right">
                <div className="ml-auto h-4 w-10 animate-pulse rounded bg-crmSurface2" />
              </td>
              <td className="px-3 py-2 text-right">
                <div className="ml-auto h-4 w-10 animate-pulse rounded bg-crmSurface2" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
          <h1 className={crmPageTitle}>Prospects</h1>
          <p className={crmPageSubtitle}>
            All prospects you can access (RLS). Updates live as the ARIA pipeline writes to CRM.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="pipeline-filter" className="text-xs font-medium uppercase text-slate-500">
            Pipeline status
          </label>
          <select
            id="pipeline-filter"
            className="rounded-lg border border-crmBorder bg-crmSurface2 px-3 py-2 text-sm text-white shadow-sm"
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
        <div className={crmTableWrap}>
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className={crmTableThead}>
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
                <tr key={p.id} className={crmTableRow}>
                  <td className="px-3 py-2">
                    <Link href={`/crm/prospects/${p.id}`} className="font-medium text-emerald-400 hover:underline">
                      {p.company_name ?? p.domain}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-400">{p.domain}</td>
                  <td className="px-3 py-2 text-slate-200">{STAGE_META[p.stage]?.label ?? p.stage}</td>
                  <td className="px-3 py-2 text-slate-300">{pipelineLabel(p.pipeline_status ?? undefined)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-300">
                    {p.lead_score != null ? p.lead_score : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-300">{p.hawk_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
