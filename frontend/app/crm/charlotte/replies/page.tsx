"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ProspectRow = {
  id: string;
  domain: string | null;
  company_name: string | null;
  contact_name: string | null;
  contact_email: string | null;
  industry: string | null;
  hawk_score: number | null;
  reply_received_at: string | null;
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

function minutesSince(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 60000);
}

function slaClass(mins: number | null) {
  if (mins === null) return "border-zinc-700";
  if (mins > 30) return "border-rose-600 bg-rose-950/40";
  if (mins >= 10) return "border-amber-500 bg-amber-950/30";
  return "border-emerald-600 bg-emerald-950/20";
}

export default function CharlotteRepliesPage() {
  const supabase = createClient();
  const [rows, setRows] = useState<ProspectRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("prospects")
      .select(
        "id,domain,company_name,contact_name,contact_email,industry,hawk_score,reply_received_at"
      )
      .not("reply_received_at", "is", null)
      .is("va_actioned_at", null)
      .order("reply_received_at", { ascending: true })
      .limit(100);
    if (error) setErr(error.message);
    else setRows((data as ProspectRow[]) || []);
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    void load();
    const ch = supabase
      .channel("prospects_va")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "prospects" },
        () => void load()
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(ch);
    };
  }, [load, supabase]);

  async function runAction(pid: string, action: "book_call" | "not_interested" | "follow_up") {
    if (!API_URL) {
      setErr("Set NEXT_PUBLIC_API_URL to call VA actions.");
      return;
    }
    setBusy(pid);
    setErr(null);
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.access_token) {
      setErr("Not signed in");
      setBusy(null);
      return;
    }
    const res = await fetch(`${API_URL}/api/crm/va/action`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ prospect_id: pid, action }),
    });
    setBusy(null);
    if (!res.ok) {
      const t = await res.text();
      setErr(t.slice(0, 400));
      return;
    }
    const j = (await res.json()) as { cal_url?: string };
    if (action === "book_call" && j.cal_url) window.open(j.cal_url, "_blank", "noopener,noreferrer");
    await load();
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Charlotte replies</h1>
        <p className="text-sm text-zinc-500">Unhandled Smartlead replies, oldest first. Target: act within 30 minutes.</p>
      </div>
      {err && <p className="text-sm text-rose-400">{err}</p>}
      {loading ? (
        <p className="text-zinc-500">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-zinc-500">No pending replies.</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((p) => {
            const mins = minutesSince(p.reply_received_at);
            return (
              <li
                key={p.id}
                className={cn("rounded-lg border p-4", slaClass(mins))}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-zinc-100">
                      {p.company_name || p.domain || "Prospect"}
                    </p>
                    <p className="text-sm text-zinc-400">
                      {p.contact_name || "—"} · {p.contact_email || "—"}
                    </p>
                    <p className="text-xs text-zinc-500">
                      Score {p.hawk_score ?? "—"} · {p.industry || "—"} · waiting {mins ?? "—"} min
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      className="bg-emerald-700 hover:bg-emerald-600"
                      disabled={busy === p.id}
                      onClick={() => void runAction(p.id, "book_call")}
                    >
                      Book call
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-zinc-600"
                      disabled={busy === p.id}
                      onClick={() => void runAction(p.id, "follow_up")}
                    >
                      Follow up
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-rose-800 text-rose-300"
                      disabled={busy === p.id}
                      onClick={() => void runAction(p.id, "not_interested")}
                    >
                      Not interested
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
