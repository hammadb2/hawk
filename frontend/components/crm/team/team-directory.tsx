"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { CrmRole, Profile } from "@/lib/crm/types";
import { cn } from "@/lib/utils";

function roleLabel(r: string): string {
  return r.replace("_", " ");
}

export function TeamDirectory() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [rows, setRows] = useState<Profile[]>([]);
  const [tlNames, setTlNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("profiles")
      .select("id, email, full_name, role, team_lead_id, status, monthly_close_target, last_close_at, created_at")
      .in("role", ["sales_rep", "team_lead"] as CrmRole[])
      .order("full_name", { ascending: true, nullsFirst: false });
    if (error) {
      toast.error(error.message);
      setRows([]);
      setLoading(false);
      return;
    }
    const list = (data ?? []) as Profile[];
    setRows(list);
    const tlIds = Array.from(new Set(list.map((p) => p.team_lead_id).filter(Boolean) as string[]));
    if (tlIds.length === 0) {
      setTlNames({});
    } else {
      const { data: tls } = await supabase.from("profiles").select("id, full_name, email").in("id", tlIds);
      const map: Record<string, string> = {};
      for (const t of tls ?? []) {
        map[t.id] = t.full_name ?? t.email ?? t.id.slice(0, 8);
      }
      setTlNames(map);
    }
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
      </div>
    );
  }

  if (!["ceo", "hos"].includes(profile.role)) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-6 text-sm text-amber-100">
        Team directory is limited to CEO and HoS. Use the scoreboard for rep standings.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          type="button"
          className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-900"
          onClick={() => void load()}
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="py-16 text-center text-zinc-500">Loading…</div>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-10 text-center text-sm text-zinc-500">
          No sales reps or team leads found.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2">Team lead</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Monthly target</th>
                <th className="px-3 py-2">Last close</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-b border-zinc-800/80 hover:bg-zinc-900/40">
                  <td className="px-3 py-2 font-medium text-zinc-100">{p.full_name ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-400">{p.email ?? "—"}</td>
                  <td className="px-3 py-2 capitalize text-zinc-300">{roleLabel(p.role)}</td>
                  <td className="px-3 py-2 text-zinc-400">
                    {p.team_lead_id ? (tlNames[p.team_lead_id] ?? p.team_lead_id.slice(0, 8)) : "—"}
                  </td>
                  <td className={cn("px-3 py-2 font-medium capitalize", p.status === "active" ? "text-emerald-400" : "text-amber-400")}>
                    {p.status}
                  </td>
                  <td className="px-3 py-2 text-zinc-400">{p.monthly_close_target ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-500">
                    {p.last_close_at ? new Date(p.last_close_at).toLocaleDateString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
