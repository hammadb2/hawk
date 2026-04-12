"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { LiveScoreboard } from "@/components/crm/scoreboard/live-scoreboard";
import { formatUsd } from "@/lib/crm/format";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type MonthOption = { label: string; start: string; end: string };

function getLastNMonths(n: number): MonthOption[] {
  const months: MonthOption[] = [];
  const now = new Date();
  for (let i = 1; i <= n; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const end = new Date(d.getFullYear(), d.getMonth() + 1, 1);
    months.push({
      label: d.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
      start: d.toISOString(),
      end: end.toISOString(),
    });
  }
  return months;
}

type HistRow = { name: string; wins: number; commission: number };

export default function ScoreboardPage() {
  const supabase = useMemo(() => createClient(), []);
  const { profile, authReady, session } = useCrmAuth();
  const months = useMemo(() => getLastNMonths(6), []);
  const [selectedMonth, setSelectedMonth] = useState(0);
  const [histRows, setHistRows] = useState<HistRow[]>([]);
  const [histLoading, setHistLoading] = useState(false);

  const loadHistory = useCallback(
    async (idx: number) => {
      if (!profile) return;
      setHistLoading(true);
      const m = months[idx];
      try {
        const [{ data: clients }, { data: reps }, commRes] = await Promise.all([
          supabase.from("clients").select("closing_rep_id, close_date, mrr_cents").gte("close_date", m.start).lt("close_date", m.end),
          supabase.from("profiles").select("id, full_name, email").in("role", ["sales_rep", "team_lead"]),
          supabase.from("crm_commissions").select("rep_id, amount_cents, created_at").gte("created_at", m.start).lt("created_at", m.end),
        ]);
        const commissions = commRes.data ?? [];
        const repMap = new Map<string, { name: string; wins: number; commission: number }>();
        for (const r of reps ?? []) {
          repMap.set(r.id, { name: (r.full_name as string) ?? (r.email as string) ?? r.id.slice(0, 8), wins: 0, commission: 0 });
        }
        for (const c of clients ?? []) {
          const rid = c.closing_rep_id as string | null;
          if (rid && repMap.has(rid)) {
            repMap.get(rid)!.wins += 1;
          }
        }
        for (const x of commissions) {
          const rid = x.rep_id as string;
          if (repMap.has(rid)) {
            repMap.get(rid)!.commission += x.amount_cents as number;
          }
        }
        const rows = Array.from(repMap.values())
          .filter((r) => r.wins > 0 || r.commission > 0)
          .sort((a, b) => b.commission - a.commission || b.wins - a.wins);
        setHistRows(rows);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to load history");
        setHistRows([]);
      } finally {
        setHistLoading(false);
      }
    },
    [profile, months, supabase]
  );

  useEffect(() => {
    if (authReady && session && profile) void loadHistory(selectedMonth);
  }, [authReady, session, profile, selectedMonth, loadHistory]);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Scoreboard</h1>
        <p className="mt-1 text-sm text-zinc-500">Live team rankings and historical performance.</p>
      </div>

      <Tabs defaultValue="live">
        <TabsList>
          <TabsTrigger value="live">Live</TabsTrigger>
          <TabsTrigger value="history">Historical</TabsTrigger>
        </TabsList>

        <TabsContent value="live">
          <LiveScoreboard />
        </TabsContent>

        <TabsContent value="history" className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {months.map((m, i) => (
              <button
                key={m.start}
                type="button"
                className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                  selectedMonth === i
                    ? "border-emerald-500 bg-emerald-500/10 text-emerald-400"
                    : "border-zinc-700 text-zinc-400 hover:bg-zinc-900"
                }`}
                onClick={() => setSelectedMonth(i)}
              >
                {m.label}
              </button>
            ))}
          </div>

          {histLoading ? (
            <div className="py-12 text-center text-zinc-500">Loading…</div>
          ) : histRows.length === 0 ? (
            <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-8 text-center text-sm text-zinc-500">
              No closed deals for {months[selectedMonth].label}.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="w-full min-w-[500px] text-left text-sm">
                <thead className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Rep</th>
                    <th className="px-3 py-2">Deals closed</th>
                    <th className="px-3 py-2">Commission earned</th>
                  </tr>
                </thead>
                <tbody>
                  {histRows.map((r, i) => (
                    <tr key={r.name} className="border-b border-zinc-800/80 hover:bg-zinc-900/40">
                      <td className="px-3 py-2 font-mono text-zinc-500">
                        {i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : i + 1}
                      </td>
                      <td className="px-3 py-2 font-medium text-zinc-100">{r.name}</td>
                      <td className="px-3 py-2 text-sky-400">{r.wins}</td>
                      <td className="px-3 py-2 font-medium text-emerald-400">{formatUsd(r.commission)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
