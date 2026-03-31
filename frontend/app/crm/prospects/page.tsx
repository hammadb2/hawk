"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import type { Prospect } from "@/lib/crm/types";
import { STAGE_META } from "@/lib/crm/types";
import toast from "react-hot-toast";

export default function ProspectsListPage() {
  const supabase = useMemo(() => createClient(), []);
  const [rows, setRows] = useState<Prospect[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase.from("prospects").select("*").order("created_at", { ascending: false });
    if (error) toast.error(error.message);
    setRows((data as Prospect[]) ?? []);
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Prospects</h1>
        <p className="text-sm text-zinc-500">All prospects you can access (RLS). Open a row for the full profile.</p>
      </div>
      {loading ? (
        <div className="flex justify-center py-12 text-zinc-500">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-800">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/80 text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-3 py-2">Company</th>
                <th className="px-3 py-2">Domain</th>
                <th className="px-3 py-2">Stage</th>
                <th className="px-3 py-2">Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-b border-zinc-800/80 hover:bg-zinc-900/40">
                  <td className="px-3 py-2">
                    <Link href={`/crm/prospects/${p.id}`} className="font-medium text-emerald-400 hover:underline">
                      {p.company_name ?? p.domain}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-zinc-400">{p.domain}</td>
                  <td className="px-3 py-2">{STAGE_META[p.stage].label}</td>
                  <td className="px-3 py-2">{p.hawk_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
