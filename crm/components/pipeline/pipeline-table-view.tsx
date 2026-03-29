"use client";

import { formatRelativeTime, stageLabel, stageBgColor, cn, getInitials } from "@/lib/utils";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { EmptyState } from "@/components/ui/empty-state";
import { useCRMStore } from "@/store/crm-store";
import { Building2 } from "lucide-react";
import type { Prospect } from "@/types/crm";

interface PipelineTableViewProps {
  prospects: Prospect[];
}

/** Dense data table for pipeline “Table” view (distinct from list layout). */
export function PipelineTableView({ prospects }: PipelineTableViewProps) {
  const { setSelectedProspect, setDrawerOpen } = useCRMStore();

  if (prospects.length === 0) {
    return (
      <EmptyState
        icon={Building2}
        title="No prospects found"
        description="Add your first prospect or adjust your filters."
        className="mt-16"
      />
    );
  }

  return (
    <div className="px-4 pb-4">
      <div className="rounded-xl border border-border overflow-hidden bg-surface-1 overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead>
            <tr className="border-b border-border bg-surface-2">
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Company</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Domain</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Industry</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">City</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Stage</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Score</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Rep</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Last Activity</th>
              <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Source</th>
            </tr>
          </thead>
          <tbody>
            {prospects.map((prospect, i) => (
              <tr
                key={prospect.id}
                onClick={() => {
                  setSelectedProspect(prospect);
                  setDrawerOpen(true);
                }}
                className={cn(
                  "cursor-pointer transition-colors hover:bg-surface-2",
                  i !== prospects.length - 1 && "border-b border-border"
                )}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {prospect.is_hot && <span className="text-yellow text-xs">★</span>}
                    <span className="text-sm font-medium text-text-primary">{prospect.company_name}</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-text-dim">{prospect.domain}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-text-secondary">{prospect.industry ?? "—"}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-text-dim">{prospect.city ?? "—"}</span>
                </td>
                <td className="px-4 py-3">
                  <span className={cn("text-xs font-medium px-2 py-0.5 rounded-md", stageBgColor(prospect.stage))}>
                    {stageLabel(prospect.stage)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <HawkScoreRing score={prospect.hawk_score} size="sm" />
                </td>
                <td className="px-4 py-3">
                  {prospect.assigned_rep ? (
                    <div className="flex items-center gap-1.5">
                      <Avatar className="w-5 h-5">
                        <AvatarFallback className="text-2xs">{getInitials(prospect.assigned_rep.name)}</AvatarFallback>
                      </Avatar>
                      <span className="text-xs text-text-secondary">{prospect.assigned_rep.name}</span>
                    </div>
                  ) : (
                    <span className="text-xs text-text-dim">Unassigned</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-text-dim">{formatRelativeTime(prospect.last_activity_at)}</span>
                </td>
                <td className="px-4 py-3">
                  <Badge
                    variant={prospect.source === "charlotte" ? "default" : "secondary"}
                    className="text-2xs capitalize"
                  >
                    {prospect.source}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
