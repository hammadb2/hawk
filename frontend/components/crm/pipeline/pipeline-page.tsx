"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDroppable,
  type DragEndEvent,
  type DragStartEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { AddProspectModal } from "@/components/crm/prospect/add-prospect-modal";
import type { Prospect, ProspectStage } from "@/lib/crm/types";
import { STAGE_META, STAGE_ORDER } from "@/lib/crm/types";
import { useCrmStore, countActiveFilters } from "@/store/crm-store";
import { ProspectCard } from "@/components/crm/pipeline/prospect-card";
import { ProspectDrawer } from "@/components/crm/prospect/prospect-drawer";
import { FilterPanel } from "@/components/crm/pipeline/filter-panel";
import { LostReasonModal } from "@/components/crm/pipeline/lost-modal";
import { CloseWonModal } from "@/components/crm/pipeline/close-won-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { bottleneckStage } from "@/lib/crm/pipeline-utils";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";

function Column({
  stage,
  children,
  count,
  value,
}: {
  stage: ProspectStage;
  children: React.ReactNode;
  count: number;
  value: number;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `stage-${stage}` });
  const meta = STAGE_META[stage];
  return (
    <div className="flex w-[280px] shrink-0 flex-col rounded-xl border border-zinc-800/80" style={{ backgroundColor: meta.columnBg }}>
      <div className="flex items-center justify-between border-b border-zinc-800/60 px-3 py-2">
        <div className="text-sm font-semibold text-zinc-100">{meta.label}</div>
        <div className="text-xs text-zinc-500">
          {count} · ${value.toLocaleString()}
        </div>
      </div>
      <div ref={setNodeRef} className={cn("flex min-h-[320px] flex-1 flex-col gap-2 p-2", isOver && "ring-1 ring-emerald-500/40")}>
        {children}
      </div>
    </div>
  );
}

function applyClientFilters(
  rows: Prospect[],
  f: ReturnType<typeof useCrmStore.getState>["filters"]
): Prospect[] {
  return rows.filter((p) => {
    if (f.repIds.length && (!p.assigned_rep_id || !f.repIds.includes(p.assigned_rep_id))) return false;
    if (f.industries.length && (!p.industry || !f.industries.some((i) => p.industry?.toLowerCase().includes(i.toLowerCase()))))
      return false;
    if (f.cities.length && (!p.city || !f.cities.some((c) => p.city?.toLowerCase().includes(c.toLowerCase())))) return false;
    if (f.stages.length && !f.stages.includes(p.stage)) return false;
    if (f.dateFrom) {
      if (new Date(p.created_at) < new Date(f.dateFrom)) return false;
    }
    if (f.dateTo) {
      if (new Date(p.created_at) > new Date(f.dateTo + "T23:59:59")) return false;
    }
    if (f.sources.length && !f.sources.includes(p.source)) return false;
    if (p.hawk_score < f.hawkMin || p.hawk_score > f.hawkMax) return false;
    return true;
  });
}

function StageList({
  byStage,
  onOpenProspect,
}: {
  byStage: Record<ProspectStage, Prospect[]>;
  onOpenProspect: (p: Prospect) => void;
}) {
  return (
    <div className="space-y-4">
      {STAGE_ORDER.map((stage) => (
        <div key={stage}>
          <div className="mb-2 text-sm font-medium text-zinc-300">{STAGE_META[stage].label}</div>
          <div className="space-y-2">
            {byStage[stage].map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => onOpenProspect(p)}
                className="w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-left text-sm transition-colors hover:border-zinc-600"
              >
                <div className="font-medium text-zinc-100">{p.company_name ?? p.domain}</div>
                <div className="text-xs text-zinc-500">{p.domain}</div>
              </button>
            ))}
            {!byStage[stage].length && <div className="text-xs text-zinc-600">Empty</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function PipelinePage() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { profile, session } = useCrmAuth();
  const { pipelineView, setPipelineView, bulkMode, setBulkMode, filters, setFilters, resetFilters } = useCrmStore();
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [reps, setReps] = useState<{ id: string; full_name: string | null; email: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [activeDrag, setActiveDrag] = useState<Prospect | null>(null);

  const [lostOpen, setLostOpen] = useState(false);
  const [pendingLost, setPendingLost] = useState<Prospect | null>(null);
  const [wonOpen, setWonOpen] = useState(false);
  const [pendingWon, setPendingWon] = useState<Prospect | null>(null);

  const [sortKey, setSortKey] = useState<"company_name" | "domain" | "stage" | "hawk_score" | "last_activity_at" | "source">(
    "last_activity_at"
  );
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const filterCount = countActiveFilters(filters);

  useEffect(() => {
    if (searchParams.get("add") === "1") {
      setAddOpen(true);
      router.replace("/crm/pipeline", { scroll: false });
    }
  }, [searchParams, router]);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase.from("prospects").select("*").order("created_at", { ascending: false });
    if (error) {
      toast.error(error.message);
      setProspects([]);
    } else {
      setProspects((data as Prospect[]) ?? []);
    }
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!profile?.id) return;
    const ch = supabase
      .channel("prospects-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "prospects" }, () => void load())
      .subscribe();
    return () => void supabase.removeChannel(ch);
  }, [supabase, profile?.id, load]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!profile || !["ceo", "hos"].includes(profile.role)) return;
    void supabase
      .from("profiles")
      .select("id, full_name, email")
      .in("role", ["sales_rep", "team_lead"])
      .then(({ data }: { data: { id: string; full_name: string | null; email: string | null }[] | null }) =>
        setReps(data ?? [])
      );
  }, [profile, supabase]);

  const filtered = useMemo(() => {
    const base = applyClientFilters(prospects, filters);
    if (!search.trim()) return base;
    const q = search.toLowerCase();
    return base.filter(
      (p) => (p.company_name && p.company_name.toLowerCase().includes(q)) || p.domain.toLowerCase().includes(q)
    );
  }, [prospects, filters, search]);

  const sortedTable = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "hawk_score":
          cmp = a.hawk_score - b.hawk_score;
          break;
        case "last_activity_at":
          cmp = new Date(a.last_activity_at).getTime() - new Date(b.last_activity_at).getTime();
          break;
        default: {
          const va = String(a[sortKey] ?? "").toLowerCase();
          const vb = String(b[sortKey] ?? "").toLowerCase();
          cmp = va < vb ? -1 : va > vb ? 1 : 0;
        }
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const byStage = useMemo(() => {
    const m = STAGE_ORDER.reduce(
      (acc, s) => {
        acc[s] = [] as Prospect[];
        return acc;
      },
      {} as Record<ProspectStage, Prospect[]>
    );
    for (const p of filtered) {
      m[p.stage].push(p);
    }
    return m;
  }, [filtered]);

  const counts = useMemo(() => {
    const c = {} as Record<ProspectStage, number>;
    STAGE_ORDER.forEach((s) => {
      c[s] = byStage[s].length;
    });
    return c;
  }, [byStage]);

  const bottleneck = useMemo(() => bottleneckStage(counts), [counts]);

  const stageValue = (list: Prospect[]) =>
    list.reduce((sum, p) => sum + (p.hawk_score >= 70 ? 5000 : p.hawk_score >= 40 ? 2500 : 1000), 0);

  async function logActivity(
    prospectId: string,
    type: string,
    metadata: Record<string, unknown>,
    notes?: string | null
  ) {
    if (!session?.user?.id) return;
    await supabase.from("activities").insert({
      prospect_id: prospectId,
      type,
      created_by: session.user.id,
      notes: notes ?? null,
      metadata,
    });
  }

  async function updateStage(p: Prospect, to: ProspectStage, extra?: Partial<Prospect>) {
    const from = p.stage;
    const { error } = await supabase
      .from("prospects")
      .update({
        stage: to,
        last_activity_at: new Date().toISOString(),
        ...extra,
      })
      .eq("id", p.id);
    if (error) {
      toast.error(error.message);
      return;
    }
    await logActivity(p.id, "stage_changed", { from, to });
    toast.success("Stage updated");
    await load();
  }

  function onDragStart(e: DragStartEvent) {
    const p = prospects.find((x) => x.id === e.active.id);
    setActiveDrag(p ?? null);
  }

  function onDragEnd(e: DragEndEvent) {
    setActiveDrag(null);
    const overId = e.over?.id;
    const activeId = String(e.active.id);
    if (!overId) return;
    const stageStr = String(overId).replace("stage-", "") as ProspectStage;
    const p = prospects.find((x) => x.id === activeId);
    if (!p || p.stage === stageStr) return;
    if (stageStr === "lost") {
      setPendingLost(p);
      setLostOpen(true);
      return;
    }
    if (stageStr === "closed_won") {
      setPendingWon(p);
      setWonOpen(true);
      return;
    }
    void updateStage(p, stageStr);
  }

  const showRepFilter = profile?.role === "ceo" || profile?.role === "hos";

  function toggleSort(key: typeof sortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  if (loading && !prospects.length) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
        <div className="flex flex-col items-center gap-2">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
          Loading pipeline…
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-50">Pipeline</h1>
          <p className="text-sm text-zinc-500">Drag cards between stages. Lost and Closed Won require confirmation.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
            {(["kanban", "list", "table"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setPipelineView(v)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium capitalize",
                  pipelineView === v ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-zinc-200"
                )}
              >
                {v}
              </button>
            ))}
          </div>
          <Button variant="outline" className="border-zinc-700" onClick={() => setAddOpen(true)}>
            Add prospect
          </Button>
          <Button variant="outline" className="border-zinc-700" onClick={() => setFilterOpen(true)}>
            Filters{filterCount ? ` (${filterCount})` : ""}
          </Button>
          <Button
            variant={bulkMode ? "default" : "outline"}
            className={cn(bulkMode ? "bg-emerald-600" : "border-zinc-700")}
            onClick={() => setBulkMode(!bulkMode)}
          >
            Bulk
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          placeholder="Search company or domain…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-md border-zinc-700 bg-zinc-900"
        />
      </div>

      {bottleneck && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          Bottleneck detected at <strong>{STAGE_META[bottleneck].label}</strong> — {counts[bottleneck]} prospects stalled vs next stage.
        </div>
      )}

      <FilterPanel
        open={filterOpen}
        onClose={() => setFilterOpen(false)}
        filters={filters}
        setFilters={setFilters}
        resetFilters={resetFilters}
        reps={reps}
        showRepFilter={showRepFilter}
      />

      {pipelineView === "kanban" && (
        <>
          <div className="hidden md:block">
            <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
              <div className="flex gap-3 overflow-x-auto pb-4">
                {STAGE_ORDER.map((stage) => (
                  <Column key={stage} stage={stage} count={byStage[stage].length} value={stageValue(byStage[stage])}>
                    {byStage[stage].map((p) => (
                      <ProspectCard
                        key={p.id}
                        prospect={p}
                        bulkMode={bulkMode}
                        selected={!!selected[p.id]}
                        onToggleSelect={() => setSelected((s) => ({ ...s, [p.id]: !s[p.id] }))}
                        now={now}
                        onOpen={(row) => setDrawerId(row.id)}
                      />
                    ))}
                  </Column>
                ))}
              </div>
              <DragOverlay>
                {activeDrag ? (
                  <div className="w-[260px] rounded-lg border border-emerald-500/50 bg-zinc-900 p-3 shadow-xl">
                    <div className="font-medium text-zinc-100">{activeDrag.company_name ?? activeDrag.domain}</div>
                    <div className="text-xs text-zinc-500">{activeDrag.domain}</div>
                  </div>
                ) : null}
              </DragOverlay>
            </DndContext>
          </div>
          <div className="md:hidden">
            <StageList byStage={byStage} onOpenProspect={(row) => setDrawerId(row.id)} />
          </div>
        </>
      )}

      {pipelineView === "list" && <StageList byStage={byStage} onOpenProspect={(row) => setDrawerId(row.id)} />}

      {pipelineView === "table" && (
        <div className="overflow-x-auto rounded-xl border border-zinc-800">
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/80 text-xs uppercase text-zinc-500">
              <tr>
                {(
                  [
                    ["company_name", "Company"],
                    ["domain", "Domain"],
                    ["stage", "Stage"],
                    ["hawk_score", "HAWK Score"],
                    ["source", "Source"],
                    ["last_activity_at", "Last activity"],
                  ] as const
                ).map(([key, label]) => (
                  <th key={key} className="px-3 py-2">
                    <button type="button" className="font-semibold hover:text-zinc-300" onClick={() => toggleSort(key)}>
                      {label}
                      {sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedTable.map((p) => (
                <tr
                  key={p.id}
                  className="cursor-pointer border-b border-zinc-800/80 hover:bg-zinc-900/50"
                  onClick={() => setDrawerId(p.id)}
                >
                  <td className="px-3 py-2 text-zinc-100">{p.company_name ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-400">{p.domain}</td>
                  <td className="px-3 py-2">{STAGE_META[p.stage].label}</td>
                  <td className="px-3 py-2">{p.hawk_score}</td>
                  <td className="px-3 py-2 capitalize">{p.source}</td>
                  <td className="px-3 py-2 text-zinc-500">{new Date(p.last_activity_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <LostReasonModal
        open={lostOpen}
        onOpenChange={setLostOpen}
        onConfirm={async ({ reason, notes, reactivateOn }) => {
          if (!pendingLost) return;
          await supabase
            .from("prospects")
            .update({
              stage: "lost",
              lost_reason: reason,
              lost_notes: notes,
              reactivate_on: reactivateOn,
              last_activity_at: new Date().toISOString(),
            })
            .eq("id", pendingLost.id);
          await logActivity(pendingLost.id, "stage_changed", { from: pendingLost.stage, to: "lost", reason });
          toast.success("Marked as lost");
          setPendingLost(null);
          await load();
        }}
      />

      <ProspectDrawer prospectId={drawerId} onClose={() => setDrawerId(null)} onUpdated={() => void load()} />

      {session?.user?.id && (
        <AddProspectModal
          open={addOpen}
          onOpenChange={setAddOpen}
          sessionUserId={session.user.id}
          onCreated={() => void load()}
        />
      )}

      <CloseWonModal
        open={wonOpen}
        onOpenChange={setWonOpen}
        onConfirm={async ({ planId, mrrCents, stripeCustomerId }) => {
          if (!pendingWon || !session?.user?.id) return;
          const planLabel = planId;
          const closer = pendingWon.assigned_rep_id ?? session.user.id;
          await supabase.from("clients").insert({
            prospect_id: pendingWon.id,
            company_name: pendingWon.company_name,
            domain: pendingWon.domain,
            plan: planLabel,
            mrr_cents: mrrCents,
            stripe_customer_id: stripeCustomerId,
            closing_rep_id: closer,
            status: "active",
          });
          await supabase
            .from("prospects")
            .update({ stage: "closed_won", last_activity_at: new Date().toISOString() })
            .eq("id", pendingWon.id);
          await logActivity(pendingWon.id, "stage_changed", { from: pendingWon.stage, to: "closed_won", plan: planLabel });
          toast.success("Client created — commission recorded (30% of MRR)");
          setPendingWon(null);
          await load();
        }}
      />
    </div>
  );
}
