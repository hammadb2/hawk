import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ProspectSource, ProspectStage } from "@/lib/crm/types";

export type PipelineView = "kanban" | "list" | "table";

export type PipelineFilters = {
  repIds: string[];
  industries: string[];
  cities: string[];
  stages: ProspectStage[];
  dateFrom: string | null;
  dateTo: string | null;
  sources: ProspectSource[];
  hawkMin: number;
  hawkMax: number;
};

const defaultFilters: PipelineFilters = {
  repIds: [],
  industries: [],
  cities: [],
  stages: [],
  dateFrom: null,
  dateTo: null,
  sources: [],
  hawkMin: 0,
  hawkMax: 100,
};

type CrmStore = {
  pipelineView: PipelineView;
  setPipelineView: (v: PipelineView) => void;
  bulkMode: boolean;
  setBulkMode: (v: boolean) => void;
  filters: PipelineFilters;
  setFilters: (f: Partial<PipelineFilters>) => void;
  resetFilters: () => void;
};

export const useCrmStore = create<CrmStore>()(
  persist(
    (set) => ({
      pipelineView: "kanban",
      setPipelineView: (pipelineView) => set({ pipelineView }),
      bulkMode: false,
      setBulkMode: (bulkMode) => set({ bulkMode }),
      filters: { ...defaultFilters },
      setFilters: (partial) => set((s) => ({ filters: { ...s.filters, ...partial } })),
      resetFilters: () => set({ filters: { ...defaultFilters } }),
    }),
    { name: "hawk-crm-ui", partialize: (s) => ({ pipelineView: s.pipelineView }) }
  )
);

export function countActiveFilters(f: PipelineFilters): number {
  let n = 0;
  if (f.repIds.length) n++;
  if (f.industries.length) n++;
  if (f.cities.length) n++;
  if (f.stages.length) n++;
  if (f.dateFrom || f.dateTo) n++;
  if (f.sources.length) n++;
  if (f.hawkMin > 0 || f.hawkMax < 100) n++;
  return n;
}
