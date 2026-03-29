"use client";

import { formatRelativeTime, stageLabel, stageBgColor, cn, getInitials } from "@/lib/utils";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { EmptyState } from "@/components/ui/empty-state";
import { Checkbox } from "@/components/ui/checkbox";
import { useCRMStore } from "@/store/crm-store";
import { Building2 } from "lucide-react";
import type { Prospect } from "@/types/crm";

interface PipelineListViewProps {
  prospects: Prospect[];
  bulkMode?: boolean;
  selectedIds?: Set<string>;
  onToggleBulkSelect?: (id: string) => void;
}

/** Scrollable list layout (not the full data table). */
export function PipelineListView({
  prospects,
  bulkMode,
  selectedIds,
  onToggleBulkSelect,
}: PipelineListViewProps) {
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
    <div className="px-4 pb-4 space-y-2">
      {prospects.map((prospect) => (
        <div
          key={prospect.id}
          className={cn(
            "flex gap-2 items-stretch rounded-xl border border-border bg-surface-1 transition-colors",
            selectedIds?.has(prospect.id) && bulkMode && "ring-2 ring-accent/40 border-accent/30"
          )}
        >
          {bulkMode && (
            <div
              className="flex items-center pl-3 py-4"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <Checkbox
                checked={selectedIds?.has(prospect.id)}
                onCheckedChange={() => onToggleBulkSelect?.(prospect.id)}
                aria-label={`Select ${prospect.company_name}`}
              />
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              if (bulkMode) {
                onToggleBulkSelect?.(prospect.id);
                return;
              }
              setSelectedProspect(prospect);
              setDrawerOpen(true);
            }}
            className={cn(
              "flex-1 min-w-0 text-left rounded-xl p-4 transition-colors",
              "hover:bg-surface-2/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            )}
          >
          <div className="flex flex-wrap items-start gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {prospect.is_hot && <span className="text-yellow text-xs">★</span>}
                <span className="text-sm font-semibold text-text-primary truncate">{prospect.company_name}</span>
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-md", stageBgColor(prospect.stage))}>
                  {stageLabel(prospect.stage)}
                </span>
              </div>
              <p className="text-xs text-text-dim mt-1 truncate">{prospect.domain}</p>
              {(prospect.city || prospect.industry) && (
                <p className="text-2xs text-text-dim/80 mt-0.5">
                  {[prospect.city, prospect.industry].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              <HawkScoreRing score={prospect.hawk_score} size="sm" />
              {prospect.assigned_rep ? (
                <div className="flex items-center gap-1.5">
                  <Avatar className="w-6 h-6">
                    <AvatarFallback className="text-2xs">{getInitials(prospect.assigned_rep.name)}</AvatarFallback>
                  </Avatar>
                  <span className="text-xs text-text-secondary hidden sm:inline max-w-[100px] truncate">
                    {prospect.assigned_rep.name}
                  </span>
                </div>
              ) : (
                <span className="text-xs text-text-dim">Unassigned</span>
              )}
              <Badge
                variant={prospect.source === "charlotte" ? "default" : "secondary"}
                className="text-2xs capitalize hidden sm:inline-flex"
              >
                {prospect.source}
              </Badge>
            </div>
          </div>
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/60">
            <span className="text-2xs text-text-dim">Last activity {formatRelativeTime(prospect.last_activity_at)}</span>
          </div>
          </button>
        </div>
      ))}
    </div>
  );
}
