"use client";

import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
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

  if (bulkMode) {
    return (
      <div className={cn("rounded-lg bg-zinc-900/90 p-3 shadow-sm", border, selected && "ring-2 ring-emerald-500/80")}>
        <div className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 shrink-0"
            checked={selected}
            onChange={onToggleSelect}
          />
          <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(prospect)}>
            <div className="truncate font-medium text-zinc-100">{prospect.company_name ?? prospect.domain}</div>
            <div className="truncate text-xs text-zinc-500">{prospect.domain}</div>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={setNodeRef} style={style} className={cn("flex gap-1 rounded-lg bg-zinc-900/90 p-2 shadow-sm", border)}>
      <button
        type="button"
        {...listeners}
        {...attributes}
        className="mt-1 flex h-8 w-6 shrink-0 cursor-grab touch-none items-center justify-center rounded text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 active:cursor-grabbing"
        aria-label="Drag to move stage"
      >
        ⋮⋮
      </button>
      <button type="button" className="min-w-0 flex-1 rounded-md px-1 py-1 text-left" onClick={() => onOpen(prospect)}>
        <div className="truncate font-medium text-zinc-100">{prospect.company_name ?? prospect.domain}</div>
        <div className="truncate text-xs text-zinc-500">{prospect.domain}</div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
          <span
            className="rounded-full px-2 py-0.5 font-medium"
            style={{
              backgroundColor: `${STAGE_META[prospect.stage].color}22`,
              color: STAGE_META[prospect.stage].color,
            }}
          >
            {prospect.source}
          </span>
          <span>Score {prospect.hawk_score}</span>
          <span>{new Date(prospect.last_activity_at).toLocaleDateString()}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-zinc-500">
          <span className="rounded border border-zinc-800 px-1.5 py-0.5">Log call</span>
          <span className="rounded border border-zinc-800 px-1.5 py-0.5">Note</span>
          <span className="rounded border border-zinc-800 px-1.5 py-0.5">Scan</span>
        </div>
      </button>
    </div>
  );
}
