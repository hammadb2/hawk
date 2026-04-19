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
import {
  revalidateClientsCache,
  useProfiles,
  useProspects,
  useProspectsRealtimeSubscription,
} from "@/lib/crm/hooks";
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
import { provisionClientPortalAfterCloseWon } from "@/lib/crm/provision-portal";
import { cn } from "@/lib/utils";
import { crmSurfaceCard, crmTableRow, crmTableThead, crmTableWrap } from "@/lib/crm/crm-surface";

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
    <div className="flex w-[280px] shrink-0 flex-col rounded-xl border border-[#1e1e2e] bg-[#111118]">
      <div className="flex items-center justify-between border-b border-[#1e1e2e] px-3 py-2">
        <div className="text-sm font-semibold text-white">{meta.label}</div>
        <div className="text-xs text-slate-500">
          {count} · ${value.toLocaleString()}
        </div>
      </div>
      <div
        ref={setNodeRef}
        className={cn(
          "flex min-h-[320px] flex-1 flex-col gap-2 p-2 transition-colors",
          isOver && "rounded-lg border border-emerald-500/50 bg-emerald-500/5",
        )}
      >
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
          <div className="mb-2 text-sm font-medium text-slate-300">{STAGE_META[stage].label}</div>
          <div className="space-y-2">
            {byStage[stage].map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => onOpenProspect(p)}
                className="w-full rounded-xl border border-[#1e1e2e] bg-[#16161f] px-3 py-2 text-left text-sm transition-colors hover:border-emerald-500/30"
              >
                <div className="font-semibold text-white">{p.company_name ?? p.domain}</div>
                <div className="text-xs text-slate-500">{p.domain}</div>
              </button>
            ))}
            {!byStage[stage].length && <div className="text-xs text-slate-600">Empty</div>}
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
  const { data: prospects = [], isLoading, mutate, error } = useProspects();
  const { data: profileRows = [] } = useProfiles();
  const { pipelineView, setPipelineView, bulkMode, setBulkMode, filters, setFilters, resetFilters } = useCrmStore();
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

  const reps = useMemo(() => {
    if (!profile || !["ceo", "hos"].includes(profile.role)) return [];
    return profileRows
      .filter((r) => r.role === "sales_rep" || r.role === "team_lead")
      .map((r) => ({ id: r.id, full_name: r.full_name, email: r.email }));
  }, [profile, profileRows]);

  useProspectsRealtimeSubscription(!!session);

  useEffect(() => {
    if (error) toast.error((error as Error).message);
  }, [error]);

  useEffect(() => {
    if (searchParams.get("add") === "1") {
      setAddOpen(true);
      router.replace("/crm/pipeline", { scroll: false });
    }
  }, [searchParams, router]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

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
    const snapshot = { ...p };
    await mutate(
      (cur) =>
        (cur ?? []).map((x) =>
          x.id === p.id ? { ...x, stage: to, last_activity_at: new Date().toISOString(), ...extra } : x
        ),
      { revalidate: false }
    );
    const { error } = await supabase
      .from("prospects")
      .update({
        stage: to,
        last_activity_at: new Date().toISOString(),
        ...extra,
      })
      .eq("id", p.id);
    if (error) {
      await mutate(
        (cur) => (cur ?? []).map((x) => (x.id === p.id ? snapshot : x)),
        { revalidate: false }
      );
      toast.error(error.message);
      return;
    }
    await logActivity(p.id, "stage_changed", { from, to });
    toast.success("Stage updated");
    void mutate();
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

  if (isLoading && !prospects.length) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded-lg bg-crmSurface" />
        <div className="flex gap-4 overflow-x-auto pb-4">
          {STAGE_ORDER.map((stage) => (
            <div key={stage} className="w-64 shrink-0 space-y-2">
              <div className="h-6 w-32 animate-pulse rounded bg-crmSurface" />
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-24 w-full animate-pulse rounded-xl bg-crmSurface2" />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Pipeline</h1>
          <p className="text-sm text-slate-400">Drag cards between stages. Lost and Closed Won require confirmation.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className={cn("flex p-0.5", crmSurfaceCard)}>
            {(["kanban", "list", "table"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setPipelineView(v)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium capitalize",
                  pipelineView === v ? "bg-emerald-500/15 text-emerald-400" : "text-slate-500 hover:text-slate-300"
                )}
              >
                {v}
              </button>
            ))}
          </div>
          <Button variant="outline" className="border-crmBorder bg-crmSurface text-slate-200 hover:bg-crmSurface2" onClick={() => setAddOpen(true)}>
            Add prospect
          </Button>
          <Button variant="outline" className="border-crmBorder bg-crmSurface text-slate-200 hover:bg-crmSurface2" onClick={() => setFilterOpen(true)}>
            Filters{filterCount ? ` (${filterCount})` : ""}
          </Button>
          <Button
            variant={bulkMode ? "default" : "outline"}
            className={cn(
              bulkMode ? "bg-emerald-600 text-white" : "border-crmBorder bg-crmSurface text-slate-200 hover:bg-crmSurface2",
            )}
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
          className="max-w-md border-crmBorder bg-crmSurface text-white placeholder:text-slate-500"
        />
      </div>

      {bottleneck && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
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
                  <div className="w-[260px] rounded-xl border border-[#1e1e2e] bg-[#16161f] p-3 shadow-xl">
                    <div className="font-semibold text-white">{activeDrag.company_name ?? activeDrag.domain}</div>
                    <div className="text-xs text-slate-500">{activeDrag.domain}</div>
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
        <div className={crmTableWrap}>
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead className={crmTableThead}>
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
                    <button type="button" className="font-semibold text-slate-300 hover:text-white" onClick={() => toggleSort(key)}>
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
                  className={cn("cursor-pointer", crmTableRow)}
                  onClick={() => setDrawerId(p.id)}
                >
                  <td className="px-3 py-2 text-white">{p.company_name ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-400">{p.domain}</td>
                  <td className="px-3 py-2">{STAGE_META[p.stage].label}</td>
                  <td className="px-3 py-2">{p.hawk_score}</td>
                  <td className="px-3 py-2 capitalize">{p.source}</td>
                  <td className="px-3 py-2 text-slate-400">{new Date(p.last_activity_at).toLocaleString()}</td>
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
          void mutate();
        }}
      />

      <ProspectDrawer prospectId={drawerId} onClose={() => setDrawerId(null)} onUpdated={() => void mutate()} />

      {session?.user?.id && (
        <AddProspectModal
          open={addOpen}
          onOpenChange={setAddOpen}
          sessionUserId={session.user.id}
          onCreated={() => void mutate()}
        />
      )}

      <CloseWonModal
        open={wonOpen}
        onOpenChange={setWonOpen}
        accessToken={session?.access_token ?? null}
        prospectDomain={pendingWon?.domain ?? ""}
        onConfirm={async ({ planId, mrrCents, stripeCustomerId, commissionDeferred }) => {
          if (!pendingWon || !session?.user?.id) return;
          const planLabel = planId;
          const closer = pendingWon.assigned_rep_id ?? session.user.id;
          const { data: newClient, error: clientErr } = await supabase
            .from("clients")
            .insert({
              prospect_id: pendingWon.id,
              company_name: pendingWon.company_name,
              domain: pendingWon.domain,
              plan: planLabel,
              mrr_cents: mrrCents,
              stripe_customer_id: stripeCustomerId,
              closing_rep_id: closer,
              status: "active",
              commission_deferred: commissionDeferred,
            })
            .select("id")
            .single();
          if (clientErr || !newClient?.id) {
            toast.error(clientErr?.message ?? "Could not create client");
            return;
          }
          await supabase
            .from("prospects")
            .update({ stage: "closed_won", last_activity_at: new Date().toISOString() })
            .eq("id", pendingWon.id);
          await logActivity(pendingWon.id, "stage_changed", { from: pendingWon.stage, to: "closed_won", plan: planLabel });
          const baseMsg = commissionDeferred
            ? "Client created — commission will post when Stripe payment clears"
            : "Client created — commission recorded (30% of MRR)";
          const prov = await provisionClientPortalAfterCloseWon(newClient.id);
          if (prov.ok) {
            const portalNote =
              prov.idempotent && !prov.invited_email
                ? " Portal already linked."
                : prov.invited_email
                  ? ` Portal invite sent to ${prov.invited_email}.`
                  : " Portal invite sent.";
            toast.success(baseMsg + portalNote);
          } else {
            toast.success(baseMsg);
            toast.error(`Portal setup: ${prov.detail}`);
          }
          setPendingWon(null);
          void mutate();
          void revalidateClientsCache();
        }}
      />
    </div>
  );
}
