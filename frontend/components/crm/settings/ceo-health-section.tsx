"use client";

/** CRM Settings — CEO-only `system_health_log` monitor table (Phase 3). */

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { SystemHealthLogRow } from "@/lib/crm/types";
import { crmSurfaceCard, crmTableRow, crmTableThead } from "@/lib/crm/crm-surface";

export function CeoHealthSection() {
  const { profile } = useCrmAuth();
  const [rows, setRows] = useState<SystemHealthLogRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (profile?.role !== "ceo") return;
    const supabase = createClient();
    void (async () => {
      const { data, error } = await supabase
        .from("system_health_log")
        .select("id,service,status,response_ms,checked_at,detail,alert_sent")
        .order("checked_at", { ascending: false })
        .limit(80);
      if (error) setErr(error.message);
      else setRows((data as SystemHealthLogRow[]) ?? []);
    })();
  }, [profile?.role]);

  if (profile?.role !== "ceo") return null;

  return (
    <section className={`p-5 ${crmSurfaceCard}`}>
      <h2 className="text-sm font-semibold text-white">Integration monitor</h2>
      <p className="mt-1 text-xs text-slate-400">
        Latest checks from <code className="text-slate-500">POST /api/monitor/health-check</code> (Railway cron +{" "}
        <code className="text-slate-500">X-Cron-Secret</code>). CEO-only.
      </p>
      {err && <p className="mt-2 text-sm text-rose-400">{err}</p>}
      {!err && rows.length === 0 && <p className="mt-3 text-sm text-slate-400">No rows yet — run the monitor cron.</p>}
      {rows.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-400">
            <thead className={crmTableThead}>
              <tr>
                <th className="py-2 pr-2">Time</th>
                <th className="py-2 pr-2">Service</th>
                <th className="py-2 pr-2">Status</th>
                <th className="py-2 pr-2">ms</th>
                <th className="py-2">Alert</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={crmTableRow}>
                  <td className="py-2 pr-2 whitespace-nowrap text-slate-300">{new Date(r.checked_at).toLocaleString()}</td>
                  <td className="py-2 pr-2 font-mono text-slate-300">{r.service}</td>
                  <td className="py-2 pr-2">
                    <span
                      className={
                        r.status === "ok"
                          ? "text-emerald-400"
                          : r.status === "degraded"
                            ? "text-amber-400"
                            : "text-rose-400"
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="py-2 pr-2">{r.response_ms ?? "—"}</td>
                  <td className="py-2">{r.alert_sent ? "yes" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
