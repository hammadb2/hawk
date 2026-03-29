"use client";

import { useState, useCallback } from "react";
import { DragDropContext, Droppable, Draggable, type DropResult } from "@hello-pangea/dnd";
import { cn, stageLabel, formatCurrency } from "@/lib/utils";
import { ESTIMATED_PIPELINE_VALUE_PER_PROSPECT } from "@/lib/pipeline-constants";
import { ProspectCard } from "./prospect-card";
import { LostModal } from "./lost-modal";
import { CloseWonModal } from "./close-won-modal";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { EmptyState } from "@/components/ui/empty-state";
import { Building2 } from "lucide-react";
import type { PipelineStage, Prospect } from "@/types/crm";

const STAGES: { id: PipelineStage; color: string; headerColor: string }[] = [
  { id: "new", color: "border-t-text-dim", headerColor: "text-text-secondary" },
  { id: "scanned", color: "border-t-blue", headerColor: "text-blue" },
  { id: "loom_sent", color: "border-t-accent", headerColor: "text-accent-light" },
  { id: "replied", color: "border-t-[#2DD4BF]", headerColor: "text-[#2DD4BF]" },
  { id: "call_booked", color: "border-t-yellow", headerColor: "text-yellow" },
  { id: "proposal_sent", color: "border-t-orange", headerColor: "text-orange" },
  { id: "closed_won", color: "border-t-green", headerColor: "text-green" },
  { id: "lost", color: "border-t-red", headerColor: "text-red" },
];

interface KanbanBoardProps {
  prospects: Prospect[];
  bulkMode?: boolean;
  selectedIds?: Set<string>;
  onToggleBulkSelect?: (id: string) => void;
}

export function KanbanBoard({
  prospects,
  bulkMode,
  selectedIds,
  onToggleBulkSelect,
}: KanbanBoardProps) {
  const { moveProspect, updateProspect } = useCRMStore();
  const [lostModalOpen, setLostModalOpen] = useState(false);
  const [closeWonModalOpen, setCloseWonModalOpen] = useState(false);
  const [pendingDrop, setPendingDrop] = useState<{
    prospectId: string;
    targetStage: PipelineStage;
  } | null>(null);

  const getProspectsByStage = useCallback(
    (stage: PipelineStage) => prospects.filter((p) => p.stage === stage),
    [prospects]
  );

  const handleDragEnd = async (result: DropResult) => {
    const { destination, source, draggableId } = result;

    if (!destination) return;
    if (
      destination.droppableId === source.droppableId &&
      destination.index === source.index
    )
      return;

    const targetStage = destination.droppableId as PipelineStage;

    // Intercept special stages
    if (targetStage === "lost") {
      const prospect = prospects.find((p) => p.id === draggableId);
      if (prospect) {
        setPendingDrop({ prospectId: draggableId, targetStage });
        setLostModalOpen(true);
      }
      return;
    }

    if (targetStage === "closed_won") {
      const prospect = prospects.find((p) => p.id === draggableId);
      if (prospect) {
        setPendingDrop({ prospectId: draggableId, targetStage });
        setCloseWonModalOpen(true);
      }
      return;
    }

    // Optimistic update
    moveProspect(draggableId, targetStage);

    try {
      const result2 = await prospectsApi.move(draggableId, targetStage);
      if (!result2.success) {
        // Revert
        moveProspect(draggableId, source.droppableId as PipelineStage);
        toast({ title: result2.error || "Failed to move prospect", variant: "destructive" });
      }
    } catch {
      moveProspect(draggableId, source.droppableId as PipelineStage);
      toast({ title: "Network error", variant: "destructive" });
    }
  };

  const pendingProspect = pendingDrop
    ? prospects.find((p) => p.id === pendingDrop.prospectId) ?? null
    : null;

  return (
    <>
      <DragDropContext onDragEnd={handleDragEnd}>
        <div className="flex gap-3 px-4 pb-4 overflow-x-auto h-full min-h-0">
          {STAGES.map((stage) => {
            const stageProspects = getProspectsByStage(stage.id);
            const stageValue = stageProspects.length * ESTIMATED_PIPELINE_VALUE_PER_PROSPECT;

            return (
              <div
                key={stage.id}
                className="flex flex-col flex-shrink-0 w-64 min-h-0"
              >
                {/* Column header */}
                <div className={cn(
                  "rounded-t-xl border-t-2 border-x border-border bg-surface-1 px-3 py-2.5 flex flex-col gap-0.5",
                  stage.color
                )}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={cn("text-xs font-semibold", stage.headerColor)}>
                      {stageLabel(stage.id)}
                    </span>
                    <span className="text-xs font-medium text-text-dim bg-surface-3 rounded-md px-1.5 py-0.5 tabular-nums">
                      {stageProspects.length}
                    </span>
                  </div>
                  <p className="text-2xs text-text-dim tabular-nums">
                    ~{formatCurrency(stageValue)} pipeline
                  </p>
                </div>

                {/* Droppable area */}
                <Droppable droppableId={stage.id}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={cn(
                        "flex-1 overflow-y-auto rounded-b-xl border-x border-b border-border p-2 space-y-2 min-h-[200px] transition-colors scrollbar-hide",
                        snapshot.isDraggingOver
                          ? "bg-accent/5 border-accent/30"
                          : "bg-surface-1/50"
                      )}
                    >
                      {stageProspects.length === 0 && !snapshot.isDraggingOver && (
                        <div className="flex items-center justify-center h-24 text-text-dim">
                          <span className="text-xs">Drop here</span>
                        </div>
                      )}

                      {stageProspects.map((prospect, index) => (
                        <Draggable
                          key={prospect.id}
                          draggableId={prospect.id}
                          index={index}
                        >
                          {(dragProvided, dragSnapshot) => (
                            <div
                              ref={dragProvided.innerRef}
                              {...dragProvided.draggableProps}
                              {...dragProvided.dragHandleProps}
                            >
                              <ProspectCard
                                prospect={prospect}
                                isDragging={dragSnapshot.isDragging}
                                bulkMode={bulkMode}
                                bulkSelected={selectedIds?.has(prospect.id)}
                                onBulkToggle={onToggleBulkSelect}
                              />
                            </div>
                          )}
                        </Draggable>
                      ))}
                      {provided.placeholder}
                    </div>
                  )}
                </Droppable>
              </div>
            );
          })}
        </div>
      </DragDropContext>

      <LostModal
        open={lostModalOpen}
        onClose={() => {
          setLostModalOpen(false);
          setPendingDrop(null);
        }}
        prospect={pendingProspect}
        onConfirm={() => setPendingDrop(null)}
      />

      <CloseWonModal
        open={closeWonModalOpen}
        onClose={() => {
          setCloseWonModalOpen(false);
          setPendingDrop(null);
        }}
        prospect={pendingProspect}
        onConfirm={() => setPendingDrop(null)}
      />
    </>
  );
}
