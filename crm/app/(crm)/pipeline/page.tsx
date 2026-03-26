"use client";

import { useState, useEffect, useMemo } from "react";
import { LayoutGrid, List, Table2, Filter, X, SlidersHorizontal } from "lucide-react";
import { KanbanBoard } from "@/components/pipeline/kanban-board";
import { PipelineListView } from "@/components/pipeline/pipeline-list-view";
import { ProspectDrawer } from "@/components/prospect/profile-drawer";
import { AddProspectModal } from "@/components/prospect/add-prospect-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { cn, stageLabel } from "@/lib/utils";
import type { PipelineStage } from "@/types/crm";

export default function PipelinePage() {
  const {
    prospects,
    setProspects,
    pipelineView,
    setPipelineView,
    pipelineFilters,
    setPipelineFilters,
    clearPipelineFilters,
    user,
  } = useCRMStore();

  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const result = await prospectsApi.list();
        if (result.success && result.data) {
          setProspects(result.data);
        } else {
          toast({ title: "Failed to load prospects", variant: "destructive" });
        }
      } catch {
        toast({ title: "Network error loading prospects", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [setProspects]);

  const filteredProspects = useMemo(() => {
    return prospects.filter((p) => {
      if (search) {
        const q = search.toLowerCase();
        if (!p.company_name.toLowerCase().includes(q) && !p.domain.toLowerCase().includes(q)) {
          return false;
        }
      }
      if (pipelineFilters.stage && p.stage !== pipelineFilters.stage) return false;
      if (pipelineFilters.source && p.source !== pipelineFilters.source) return false;
      if (pipelineFilters.industry && p.industry !== pipelineFilters.industry) return false;
      if (pipelineFilters.city && p.city !== pipelineFilters.city) return false;
      if (pipelineFilters.rep && p.assigned_rep_id !== pipelineFilters.rep) return false;
      if (pipelineFilters.scoreMin !== undefined && (p.hawk_score ?? 0) < pipelineFilters.scoreMin) return false;
      if (pipelineFilters.scoreMax !== undefined && (p.hawk_score ?? 100) > pipelineFilters.scoreMax) return false;
      return true;
    });
  }, [prospects, search, pipelineFilters]);

  const activeFilterCount = Object.values(pipelineFilters).filter(Boolean).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex-1">
          <h1 className="text-base font-semibold text-text-primary">Pipeline</h1>
          <p className="text-xs text-text-dim">{filteredProspects.length} prospects</p>
        </div>

        {/* Search */}
        <div className="w-56">
          <Input
            placeholder="Search prospects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 text-xs"
          />
        </div>

        {/* View toggle */}
        <div className="flex items-center gap-0.5 bg-surface-2 border border-border rounded-lg p-0.5">
          {[
            { id: "kanban" as const, icon: LayoutGrid, label: "Kanban" },
            { id: "list" as const, icon: List, label: "List" },
            { id: "table" as const, icon: Table2, label: "Table" },
          ].map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setPipelineView(id)}
              title={label}
              className={cn(
                "flex items-center justify-center w-7 h-7 rounded transition-all",
                pipelineView === id
                  ? "bg-surface-3 text-text-primary"
                  : "text-text-dim hover:text-text-secondary"
              )}
            >
              <Icon className="w-3.5 h-3.5" />
            </button>
          ))}
        </div>

        {/* Filters */}
        <Button
          variant="secondary"
          size="sm"
          className="gap-1.5 h-8 text-xs"
          onClick={() => {}}
        >
          <Filter className="w-3.5 h-3.5" />
          Filters
          {activeFilterCount > 0 && (
            <span className="w-4 h-4 rounded-full bg-accent text-white text-2xs flex items-center justify-center">
              {activeFilterCount}
            </span>
          )}
        </Button>

        <Button size="sm" className="h-8 text-xs" onClick={() => setAddOpen(true)}>
          + Add Prospect
        </Button>
      </div>

      {/* Active filters chips */}
      {activeFilterCount > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border flex-shrink-0 flex-wrap">
          <span className="text-xs text-text-dim">Filters:</span>
          {pipelineFilters.stage && (
            <Badge variant="secondary" className="gap-1 text-xs">
              Stage: {stageLabel(pipelineFilters.stage as PipelineStage)}
              <button onClick={() => setPipelineFilters({ ...pipelineFilters, stage: undefined })}>
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          {pipelineFilters.source && (
            <Badge variant="secondary" className="gap-1 text-xs capitalize">
              Source: {pipelineFilters.source}
              <button onClick={() => setPipelineFilters({ ...pipelineFilters, source: undefined })}>
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          <button
            onClick={clearPipelineFilters}
            className="text-xs text-text-dim hover:text-text-secondary transition-colors ml-1"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {pipelineView === "kanban" ? (
          <div className="h-full overflow-hidden pt-4">
            <KanbanBoard prospects={filteredProspects} />
          </div>
        ) : (
          <div className="h-full overflow-y-auto pt-4">
            <PipelineListView prospects={filteredProspects} />
          </div>
        )}
      </div>

      {/* Drawer */}
      <ProspectDrawer />

      {/* Add prospect modal */}
      <AddProspectModal open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}
