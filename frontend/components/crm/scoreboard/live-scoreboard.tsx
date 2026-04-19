"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { formatUsd } from "@/lib/crm/format";
import type { CrmRole } from "@/lib/crm/types";
import { crmEmptyState, crmTableRow, crmTableThead, crmTableWrap } from "@/lib/crm/crm-surface";

const CLOSED = new Set(["lost", "closed_won"]);

type RepProfile = {
  id: string;
  full_name: string | null;
  email: string | null;
  role: string;
};

type ScoreRow = {
  repId: string;
  name: string;
  pipeline: number;
  monthlyWins: number;
  activeClients: number;
  pendingCents: number;
};

function monthStartIso(): string {
  const d = new Date();
  d.setDate(1);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

async function loadRepsForRole(
  supabase: ReturnType<typeof createClient>,
  profile: { id: string; role: CrmRole }
): Promise<RepProfile[]> {
  const base = supabase.from("profiles").select("id, full_name, email, role").eq("status", "active").in("role", ["sales_rep", "team_lead"]);

  if (profile.role === "sales_rep") {
    const { data, error } = await supabase
      .from("profiles")
      .select("id, full_name, email, role")
      .eq("id", profile.id)
      .maybeSingle();
    if (error) throw error;
    return data ? [data as RepProfile] : [];
  }

  if (profile.role === "team_lead") {
    const { data, error } = await supabase
      .from("profiles")
      .select("id, full_name, email, role")
      .eq("status", "active")
      .or(`team_lead_id.eq.${profile.id},id.eq.${profile.id}`)
      .in("role", ["sales_rep", "team_lead"]);
    if (error) throw error;
    return (data ?? []) as RepProfile[];
  }

  const { data, error } = await base;
  if (error) throw error;
  return (data ?? []) as RepProfile[];
}

export function LiveScoreboard() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [rows, setRows] = useState<ScoreRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    try {
      const reps = await loadRepsForRole(supabase, profile);
      const repIds = new Set(reps.map((r) => r.id));
      if (repIds.size === 0) {
        setRows([]);
        setUpdatedAt(new Date());
        setLoading(false);
        return;
      }

      const start = monthStartIso();

      const { data: prospects, error: e1 } = await supabase.from("prospects").select("assigned_rep_id, stage");
      const { data: clients, error: e2 } = await supabase.from("clients").select("closing_rep_id, close_date, status");
      const commRes = await supabase.from("crm_commissions").select("rep_id, amount_cents, status");

      if (e1) throw e1;
      if (e2) throw e2;

      let commissions = commRes.data ?? [];
      if (commRes.error) {
        const msg = commRes.error.message ?? "";
        if (msg.includes("crm_commissions") || msg.includes("does not exist") || commRes.error.code === "PGRST205") {
          toast.error("Apply Phase 4 migration so commission totals appear on the scoreboard.");
          commissions = [];
        } else {
          throw commRes.error;
        }
      }

      const pipeline: Record<string, number> = {};
      for (const p of prospects ?? []) {
        const aid = p.assigned_rep_id as string | null;
        if (!aid || !repIds.has(aid)) continue;
        if (CLOSED.has(p.stage as string)) continue;
        pipeline[aid] = (pipeline[aid] ?? 0) + 1;
      }

      const monthlyWins: Record<string, number> = {};
      const activeClients: Record<string, number> = {};
      for (const c of clients ?? []) {
        const cid = c.closing_rep_id as string | null;
        if (!cid || !repIds.has(cid)) continue;
        if ((c.close_date as string) >= start) {
          monthlyWins[cid] = (monthlyWins[cid] ?? 0) + 1;
        }
        if (c.status === "active") {
          activeClients[cid] = (activeClients[cid] ?? 0) + 1;
        }
      }

      const pendingCents: Record<string, number> = {};
      for (const x of commissions ?? []) {
        const rid = x.rep_id as string;
        if (!repIds.has(rid)) continue;
        if (x.status !== "pending") continue;
        pendingCents[rid] = (pendingCents[rid] ?? 0) + (x.amount_cents as number);
      }

      const built: ScoreRow[] = reps.map((r) => ({
        repId: r.id,
        name: r.full_name ?? r.email ?? r.id.slice(0, 8),
        pipeline: pipeline[r.id] ?? 0,
        monthlyWins: monthlyWins[r.id] ?? 0,
        activeClients: activeClients[r.id] ?? 0,
        pendingCents: pendingCents[r.id] ?? 0,
      }));

      built.sort((a, b) => {
        if (b.pendingCents !== a.pendingCents) return b.pendingCents - a.pendingCents;
        if (b.pipeline !== a.pipeline) return b.pipeline - a.pipeline;
        return a.name.localeCompare(b.name);
      });

      setRows(built);
      setUpdatedAt(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Load failed";
      toast.error(msg);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [profile, supabase]);

  useEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  useEffect(() => {
    if (!authReady || !session || !profile) return;
    const ch = supabase
      .channel("crm-scoreboard")
      .on("postgres_changes", { event: "*", schema: "public", table: "prospects" }, () => void load())
      .on("postgres_changes", { event: "*", schema: "public", table: "clients" }, () => void load())
      .on("postgres_changes", { event: "*", schema: "public", table: "crm_commissions" }, () => void load())
      .subscribe();
    return () => {
      void supabase.removeChannel(ch);
    };
  }, [authReady, session, profile, supabase, load]);

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-400">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#1e1e2e] border-t-emerald-500" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-slate-400">
          Ranked by pending commission, then open pipeline count. Updates live when prospects, clients, or commissions change.
        </p>
        <div className="flex items-center gap-3 text-xs text-slate-400">
          {updatedAt && <span>Updated {updatedAt.toLocaleTimeString()}</span>}
          <button
            type="button"
            className="rounded-lg border border-[#1e1e2e] bg-[#111118] px-2 py-1 text-slate-200 hover:bg-[#1a1a24]"
            onClick={() => void load()}
          >
            Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="py-12 text-center text-slate-400">Loading…</div>
      ) : rows.length === 0 ? (
        <p className={`${crmEmptyState} py-8`}>No reps to show.</p>
      ) : (
        <div className={crmTableWrap}>
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className={crmTableThead}>
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Rep</th>
                <th className="px-3 py-2">Open pipeline</th>
                <th className="px-3 py-2">Closes (MTD)</th>
                <th className="px-3 py-2">Active clients</th>
                <th className="px-3 py-2">Pending commission</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.repId} className={crmTableRow}>
                  <td className="px-3 py-2 font-mono text-slate-500">{i + 1}</td>
                  <td className="px-3 py-2 font-medium text-white">{r.name}</td>
                  <td className="px-3 py-2 text-slate-300">{r.pipeline}</td>
                  <td className="px-3 py-2 text-sky-400">{r.monthlyWins}</td>
                  <td className="px-3 py-2 text-slate-300">{r.activeClients}</td>
                  <td className="px-3 py-2 font-medium text-emerald-400">{formatUsd(r.pendingCents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
