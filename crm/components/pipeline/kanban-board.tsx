"use client";

import { useState, useCallback } from "react";
import { DragDropContext, Droppable, Draggable, type DropResult } from "@hello-pangea/dnd";
import { AlertTriangle, TrendingDown } from "lucide-react";
import { cn, stageLabel, formatCurrency, agingBorderColor } from "@/lib/utils";
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
}

export function KanbanBoard({ prospects }: KanbanBoardProps) {
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

  // Bottleneck detection: if any stage has 3x more than next stage
  const bottlenecks = STAGES.slice(0, -2).reduce<PipelineStage[]>((acc, stage, i) => {
    const count = getProspectsByStage(stage.id).length;
    const nextCount = getProspectsByStage(STAGES[i + 1].id).length;
    if (count > 0 && nextCount > 0 && count >= nextCount * 3) {
      acc.push(stage.id);
    }
    return acc;
  }, []);

  const pendingProspect = pendingDrop
    ? prospects.find((p) => p.id === pendingDrop.prospectId) ?? null
    : null;

  return (
    <>
      {/* Bottleneck alert */}
      {bottlenecks.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 bg-yellow/10 border border-yellow/25 rounded-lg mb-4 mx-4">
          <AlertTriangle className="w-4 h-4 text-yellow flex-shrink-0" />
          <p className="text-xs text-yellow">
            Pipeline bottleneck detected in: {bottlenecks.map(stageLabel).join(", ")}
          </p>
        </div>
      )}

      <DragDropContext onDragEnd={handleDragEnd}>
        <div className="flex gap-3 px-4 pb-4 overflow-x-auto h-full min-h-0">
          {STAGES.map((stage) => {
            const stageProspects = getProspectsByStage(stage.id);
            const totalValue = stageProspects.reduce((sum, p) => {
              // Estimate based on common plan value
              return sum + 199; // placeholder
            }, 0);

            return (
              <div
                key={stage.id}
                className="flex flex-col flex-shrink-0 w-64 min-h-0"
              >
                {/* Column header */}
                <div className={cn(
                  "rounded-t-xl border-t-2 border-x border-border bg-surface-1 px-3 py-2.5 flex items-center justify-between",
                  stage.color
                )}>
                  <div>
                    <span className={cn("text-xs font-semibold", stage.headerColor)}>
                      {stageLabel(stage.id)}
                    </span>
                  </div>
                  <span className="text-xs font-medium text-text-dim bg-surface-3 rounded-md px-1.5 py-0.5">
                    {stageProspects.length}
                  </span>
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
