"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ProspectSource } from "@/lib/crm/types";
import { STAGE_META, STAGE_ORDER } from "@/lib/crm/types";
import type { PipelineFilters } from "@/store/crm-store";
import { countActiveFilters } from "@/store/crm-store";

type RepOption = { id: string; full_name: string | null; email: string | null };

export function FilterPanel({
  open,
  onClose,
  filters,
  setFilters,
  resetFilters,
  reps,
  showRepFilter,
}: {
  open: boolean;
  onClose: () => void;
  filters: PipelineFilters;
  setFilters: (f: Partial<PipelineFilters>) => void;
  resetFilters: () => void;
  reps: RepOption[];
  showRepFilter: boolean;
}) {
  if (!open) return null;

  const toggleArray = <T extends string>(arr: T[], val: T): T[] =>
    arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val];

  const active = countActiveFilters(filters);

  return (
    <>
      <button type="button" className="fixed inset-0 z-40 bg-black/50 md:hidden" aria-label="Close filters" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-zinc-800 bg-zinc-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <h2 className="text-lg font-semibold text-zinc-100">Filters</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
          {showRepFilter && (
            <div>
              <Label className="text-zinc-300">Rep</Label>
              <div className="mt-2 flex flex-wrap gap-2">
                {reps.map((r) => {
                  const selected = filters.repIds.includes(r.id);
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setFilters({ repIds: toggleArray(filters.repIds, r.id) })}
                      className={`rounded-full border px-3 py-1 text-xs ${
                        selected ? "border-emerald-500 bg-emerald-500/10 text-emerald-300" : "border-zinc-700 text-zinc-400"
                      }`}
                    >
                      {r.full_name ?? r.email ?? r.id.slice(0, 6)}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <div>
            <Label className="text-zinc-300">Industry (comma-separated)</Label>
            <Input
              className="mt-1 border-zinc-700 bg-zinc-900"
              placeholder="e.g. Dental, Legal"
              value={filters.industries.join(", ")}
              onChange={(e) =>
                setFilters({
                  industries: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
          <div>
            <Label className="text-zinc-300">City (comma-separated)</Label>
            <Input
              className="mt-1 border-zinc-700 bg-zinc-900"
              value={filters.cities.join(", ")}
              onChange={(e) =>
                setFilters({
                  cities: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
          <div>
            <Label className="text-zinc-300">Stage</Label>
            <div className="mt-2 flex flex-wrap gap-2">
              {STAGE_ORDER.map((s) => {
                const selected = filters.stages.includes(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setFilters({ stages: toggleArray(filters.stages, s) })}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      selected ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-700 text-zinc-400"
                    }`}
                  >
                    {STAGE_META[s].label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-zinc-300">Date from</Label>
              <Input
                type="date"
                className="mt-1 border-zinc-700 bg-zinc-900"
                value={filters.dateFrom ?? ""}
                onChange={(e) => setFilters({ dateFrom: e.target.value || null })}
              />
            </div>
            <div>
              <Label className="text-zinc-300">Date to</Label>
              <Input
                type="date"
                className="mt-1 border-zinc-700 bg-zinc-900"
                value={filters.dateTo ?? ""}
                onChange={(e) => setFilters({ dateTo: e.target.value || null })}
              />
            </div>
          </div>
          <div>
            <Label className="text-zinc-300">Source</Label>
            <div className="mt-2 flex flex-wrap gap-2">
              {(["charlotte", "manual", "inbound"] as ProspectSource[]).map((s) => {
                const selected = filters.sources.includes(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setFilters({ sources: toggleArray(filters.sources, s) })}
                    className={`rounded-full border px-3 py-1 text-xs capitalize ${
                      selected ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-700 text-zinc-400"
                    }`}
                  >
                    {s}
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <Label className="text-zinc-300">
              HAWK score: {filters.hawkMin} – {filters.hawkMax}
            </Label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Input
                type="number"
                min={0}
                max={100}
                className="border-zinc-700 bg-zinc-900"
                value={filters.hawkMin}
                onChange={(e) => setFilters({ hawkMin: Number(e.target.value) || 0 })}
              />
              <Input
                type="number"
                min={0}
                max={100}
                className="border-zinc-700 bg-zinc-900"
                value={filters.hawkMax}
                onChange={(e) => setFilters({ hawkMax: Number(e.target.value) || 100 })}
              />
            </div>
          </div>
        </div>
        <div className="flex gap-2 border-t border-zinc-800 p-4">
          <Button className="flex-1 bg-emerald-600 hover:bg-emerald-500" onClick={onClose}>
            Apply {active ? `(${active})` : ""}
          </Button>
          <Button variant="outline" className="border-zinc-700" onClick={resetFilters}>
            Reset
          </Button>
        </div>
      </aside>
    </>
  );
}
