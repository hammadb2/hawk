"use client";

import { useState, useEffect, useMemo } from "react";
import { LayoutGrid, List, Table2, Filter, X } from "lucide-react";
import { KanbanBoard } from "@/components/pipeline/kanban-board";
import { PipelineListView } from "@/components/pipeline/pipeline-list-view";
import { PipelineTableView } from "@/components/pipeline/pipeline-table-view";
import { ProspectDrawer } from "@/components/prospect/profile-drawer";
import { AddProspectModal } from "@/components/prospect/add-prospect-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuthReady } from "@/components/layout/providers";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { cn, stageLabel } from "@/lib/utils";
import type { PipelineStage, ProspectSource } from "@/types/crm";

const ANY = "__any__";

const PIPELINE_STAGES: PipelineStage[] = [
  "new",
  "scanned",
  "loom_sent",
  "replied",
  "call_booked",
  "proposal_sent",
  "closed_won",
  "lost",
];

const SOURCES: ProspectSource[] = ["charlotte", "manual", "inbound", "inbound_signup", "referral"];

export default function PipelinePage() {
  const authReady = useAuthReady();
  const {
    prospects,
    setProspects,
    pipelineView,
    setPipelineView,
    pipelineFilters,
    setPipelineFilters,
    clearPipelineFilters,
  } = useCRMStore();

  const [loading, setLoading] = useState(prospects.length === 0);
  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draftFilters, setDraftFilters] = useState(pipelineFilters);

  useEffect(() => {
    if (filtersOpen) setDraftFilters(pipelineFilters);
  }, [filtersOpen, pipelineFilters]);

  useEffect(() => {
    if (!authReady) return;
    const load = async () => {
      const hasData = useCRMStore.getState().prospects.length > 0;
      if (!hasData) setLoading(true);
      try {
        const result = await prospectsApi.list();
        if (result.success && result.data) {
          setProspects(result.data);
        } else if (!hasData) {
          toast({ title: "Failed to load prospects", variant: "destructive" });
        }
      } catch {
        if (!hasData) toast({ title: "Network error loading prospects", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [authReady, setProspects]);

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

  const industries = useMemo(() => {
    const s = new Set<string>();
    prospects.forEach((p) => {
      if (p.industry) s.add(p.industry);
    });
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [prospects]);

  const cities = useMemo(() => {
    const s = new Set<string>();
    prospects.forEach((p) => {
      if (p.city) s.add(p.city);
    });
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [prospects]);

  const repOptions = useMemo(() => {
    const m = new Map<string, string>();
    prospects.forEach((p) => {
      if (p.assigned_rep_id && p.assigned_rep?.name) {
        m.set(p.assigned_rep_id, p.assigned_rep.name);
      }
    });
    return Array.from(m.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [prospects]);

  const activeFilterCount = Object.values(pipelineFilters).filter(
    (v) => v !== undefined && v !== "" && v !== null
  ).length;

  const applyFilters = () => {
    setPipelineFilters(draftFilters);
    setFiltersOpen(false);
  };

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
          onClick={() => setFiltersOpen(true)}
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

      <Dialog open={filtersOpen} onOpenChange={setFiltersOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Pipeline filters</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-text-secondary">Stage</span>
              <Select
                value={draftFilters.stage ?? ANY}
                onValueChange={(v) =>
                  setDraftFilters({ ...draftFilters, stage: v === ANY ? undefined : v })
                }
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Any stage" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>Any stage</SelectItem>
                  {PIPELINE_STAGES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {stageLabel(s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-text-secondary">Source</span>
              <Select
                value={draftFilters.source ?? ANY}
                onValueChange={(v) =>
                  setDraftFilters({ ...draftFilters, source: v === ANY ? undefined : (v as ProspectSource) })
                }
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Any source" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>Any source</SelectItem>
                  {SOURCES.map((s) => (
                    <SelectItem key={s} value={s} className="capitalize">
                      {s.replace(/_/g, " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-text-secondary">Industry</span>
              <Select
                value={draftFilters.industry ?? ANY}
                onValueChange={(v) =>
                  setDraftFilters({ ...draftFilters, industry: v === ANY ? undefined : v })
                }
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Any industry" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>Any industry</SelectItem>
                  {industries.map((ind) => (
                    <SelectItem key={ind} value={ind}>
                      {ind}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-text-secondary">City</span>
              <Select
                value={draftFilters.city ?? ANY}
                onValueChange={(v) =>
                  setDraftFilters({ ...draftFilters, city: v === ANY ? undefined : v })
                }
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Any city" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>Any city</SelectItem>
                  {cities.map((city) => (
                    <SelectItem key={city} value={city}>
                      {city}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-text-secondary">Assigned rep</span>
              <Select
                value={draftFilters.rep ?? ANY}
                onValueChange={(v) =>
                  setDraftFilters({ ...draftFilters, rep: v === ANY ? undefined : v })
                }
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Any rep" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>Any rep</SelectItem>
                  {repOptions.map(([id, name]) => (
                    <SelectItem key={id} value={id}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <span className="text-xs font-medium text-text-secondary">Min score</span>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  placeholder="0"
                  className="h-9 text-xs"
                  value={draftFilters.scoreMin ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setDraftFilters({
                      ...draftFilters,
                      scoreMin: v === "" ? undefined : Number(v),
                    });
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <span className="text-xs font-medium text-text-secondary">Max score</span>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  placeholder="100"
                  className="h-9 text-xs"
                  value={draftFilters.scoreMax ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setDraftFilters({
                      ...draftFilters,
                      scoreMax: v === "" ? undefined : Number(v),
                    });
                  }}
                />
              </div>
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => {
                setDraftFilters({});
              }}
            >
              Reset
            </Button>
            <Button type="button" size="sm" onClick={applyFilters}>
              Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Active filters chips */}
      {activeFilterCount > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border flex-shrink-0 flex-wrap">
          <span className="text-xs text-text-dim">Filters:</span>
          {pipelineFilters.stage && (
            <Badge variant="secondary" className="gap-1 text-xs">
              Stage: {stageLabel(pipelineFilters.stage as PipelineStage)}
              <button type="button" onClick={() => setPipelineFilters({ ...pipelineFilters, stage: undefined })}>
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          {pipelineFilters.source && (
            <Badge variant="secondary" className="gap-1 text-xs capitalize">
              Source: {pipelineFilters.source}
              <button type="button" onClick={() => setPipelineFilters({ ...pipelineFilters, source: undefined })}>
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          {pipelineFilters.industry && (
            <Badge variant="secondary" className="gap-1 text-xs">
              Industry: {pipelineFilters.industry}
              <button type="button" onClick={() => setPipelineFilters({ ...pipelineFilters, industry: undefined })}>
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          {pipelineFilters.city && (
            <Badge variant="secondary" className="gap-1 text-xs">
              City: {pipelineFilters.city}
              <button type="button" onClick={() => setPipelineFilters({ ...pipelineFilters, city: undefined })}>
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          {pipelineFilters.rep && (
            <Badge variant="secondary" className="gap-1 text-xs">
              Rep: {repOptions.find(([id]) => id === pipelineFilters.rep)?.[1] ?? pipelineFilters.rep.slice(0, 8)}
              <button type="button" onClick={() => setPipelineFilters({ ...pipelineFilters, rep: undefined })}>
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          {(pipelineFilters.scoreMin !== undefined || pipelineFilters.scoreMax !== undefined) && (
            <Badge variant="secondary" className="gap-1 text-xs">
              Score: {pipelineFilters.scoreMin ?? 0}–{pipelineFilters.scoreMax ?? 100}
              <button
                type="button"
                onClick={() =>
                  setPipelineFilters({
                    ...pipelineFilters,
                    scoreMin: undefined,
                    scoreMax: undefined,
                  })
                }
              >
                <X className="w-2.5 h-2.5" />
              </button>
            </Badge>
          )}
          <button
            type="button"
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
        ) : pipelineView === "table" ? (
          <div className="h-full overflow-y-auto pt-4">
            <PipelineTableView prospects={filteredProspects} />
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
