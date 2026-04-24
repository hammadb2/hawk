"use client";

import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import type { Prospect } from "@/lib/crm/types";
import { STAGE_META } from "@/lib/crm/types";
import { agingBorderClass } from "@/lib/crm/pipeline-utils";
import { cn } from "@/lib/utils";

export function ProspectCard({
  prospect,
  bulkMode,
  selected,
  onToggleSelect,
  now,
  onOpen,
}: {
  prospect: Prospect;
  bulkMode: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  now: number;
  onOpen: (p: Prospect) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: prospect.id,
    disabled: bulkMode,
  });

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.5 : 1,
  };

  const border = agingBorderClass(prospect.last_activity_at, now);
  const hasVuln = !!(prospect.vulnerability_found && String(prospect.vulnerability_found).trim());

  if (bulkMode) {
    return (
      <div
        className={cn(
          "relative rounded-xl border border-[#1e1e2e] bg-[#16161f] p-3 shadow-lg",
          border,
          selected && "ring-2 ring-signal/80",
        )}
      >
        <div className="flex items-start gap-2">
          <input type="checkbox" className="mt-1 h-4 w-4 shrink-0" checked={selected} onChange={onToggleSelect} />
          <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(prospect)}>
            <div className="truncate font-semibold text-white">{prospect.company_name ?? prospect.domain}</div>
            <div className="truncate text-xs text-ink-0">{prospect.domain}</div>
          </button>
        </div>
        {prospect.is_hot && (
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red/100 shadow-[0_0_8px_rgba(244,63,94,0.6)]" title="Hot lead" />
        )}
        {hasVuln && (
          <span className="mt-2 inline-block rounded bg-signal/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-signal">
            VULN FOUND
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn("relative flex gap-1 rounded-xl border border-[#1e1e2e] bg-[#16161f] p-3 shadow-lg", border)}
    >
      {prospect.is_hot && (
        <span className="absolute right-2 top-2 z-10 h-2 w-2 rounded-full bg-red/100 shadow-[0_0_8px_rgba(244,63,94,0.6)]" title="Hot lead" />
      )}
      <button
        type="button"
        {...listeners}
        {...attributes}
        className="mt-0.5 flex h-8 w-7 shrink-0 cursor-grab touch-none items-center justify-center rounded text-ink-0 hover:bg-ink-800/5 hover:text-ink-100 active:cursor-grabbing"
        aria-label="Drag to move stage"
      >
        <GripVertical className="h-4 w-4" strokeWidth={2} />
      </button>
      <button type="button" className="min-w-0 flex-1 rounded-md px-1 py-0.5 text-left" onClick={() => onOpen(prospect)}>
        <div className="flex flex-wrap items-start justify-between gap-2 pr-4">
          <div className="min-w-0 flex-1">
            <div className="truncate font-semibold text-white">{prospect.company_name ?? prospect.domain}</div>
            <div className="truncate text-xs text-ink-0">{prospect.domain}</div>
          </div>
          {hasVuln && (
            <span className="shrink-0 rounded bg-signal/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-signal">
              VULN FOUND
            </span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-0">
          <span
            className="rounded-full px-2 py-0.5 font-medium"
            style={{
              backgroundColor: `${STAGE_META[prospect.stage].color}22`,
              color: STAGE_META[prospect.stage].color,
            }}
          >
            {prospect.source}
          </span>
          {prospect.stage === "scanning" ? (
            <span className="inline-flex items-center gap-1 text-signal">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-signal-300" />
              Scanning…
            </span>
          ) : prospect.hawk_score > 0 || prospect.scanned_at ? (
            <span>Score {prospect.hawk_score}</span>
          ) : (
            <span className="text-ink-200">Unscanned</span>
          )}
          <span>{new Date(prospect.last_activity_at).toLocaleDateString()}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-ink-0">
          <span className="rounded border border-[#1e1e2e] px-1.5 py-0.5">Log call</span>
          <span className="rounded border border-[#1e1e2e] px-1.5 py-0.5">Note</span>
          <span className="rounded border border-[#1e1e2e] px-1.5 py-0.5">Scan</span>
        </div>
      </button>
    </div>
  );
}
