"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CrmSupportTicketRow } from "@/lib/crm/types";
import { cn } from "@/lib/utils";

const STATUSES: CrmSupportTicketRow["status"][] = ["open", "in_progress", "resolved", "closed"];
const PRIOS: CrmSupportTicketRow["priority"][] = ["low", "normal", "high"];

function privileged(role: string | undefined) {
  return role === "ceo" || role === "hos";
}

export function SupportTicketsConsole() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [rows, setRows] = useState<CrmSupportTicketRow[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [priority, setPriority] = useState<CrmSupportTicketRow["priority"]>("normal");
  const [saving, setSaving] = useState(false);

  const isExec = privileged(profile?.role);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase.from("crm_support_tickets").select("*").order("created_at", { ascending: false });
    if (error) {
      if (error.message.includes("crm_support_tickets") || error.code === "PGRST205") {
        toast.error("Apply the CRM support tickets migration (crm_support_tickets).");
      } else {
        toast.error(error.message);
      }
      setRows([]);
      setLoading(false);
      return;
    }
    const list = (data ?? []) as CrmSupportTicketRow[];
    setRows(list);
    if (isExec && list.length > 0) {
      const ids = Array.from(new Set(list.map((r) => r.requester_id)));
      const { data: profs } = await supabase.from("profiles").select("id, full_name, email").in("id", ids);
      const map: Record<string, string> = {};
      for (const p of profs ?? []) {
        map[p.id] = p.full_name ?? p.email ?? p.id.slice(0, 8);
      }
      setNames(map);
    } else {
      setNames({});
    }
    setLoading(false);
  }, [supabase, isExec]);

  useEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  async function createTicket(e: React.FormEvent) {
    e.preventDefault();
    if (!session?.user?.id || !subject.trim()) return;
    setSaving(true);
    try {
      const { error } = await supabase.from("crm_support_tickets").insert({
        subject: subject.trim(),
        body: body.trim(),
        priority,
        requester_id: session.user.id,
      });
      if (error) {
        toast.error(error.message);
        return;
      }
      toast.success("Ticket submitted — leadership has been notified.");
      setSubject("");
      setBody("");
      setPriority("normal");
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function patchTicket(id: string, patch: Partial<Pick<CrmSupportTicketRow, "status" | "priority">>) {
    const { error } = await supabase.from("crm_support_tickets").update(patch).eq("id", id);
    if (error) {
      toast.error(error.message);
      return;
    }
    toast.success("Updated");
    await load();
  }

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
        <h2 className="text-sm font-semibold text-zinc-200">New ticket</h2>
        <p className="mt-1 text-xs text-zinc-500">Describe the issue. CEO and HoS get an in-app notification.</p>
        <form className="mt-4 space-y-3" onSubmit={(e) => void createTicket(e)}>
          <div>
            <Label className="text-zinc-400">Subject</Label>
            <Input className="mt-1 border-zinc-700 bg-zinc-900" value={subject} onChange={(e) => setSubject(e.target.value)} required />
          </div>
          <div>
            <Label className="text-zinc-400">Details</Label>
            <textarea
              className="mt-1 min-h-[100px] w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-zinc-400">Priority</Label>
            <select
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
              value={priority}
              onChange={(e) => setPriority(e.target.value as CrmSupportTicketRow["priority"])}
            >
              {PRIOS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" className="bg-emerald-600" disabled={saving}>
            {saving ? "Submitting…" : "Submit ticket"}
          </Button>
        </form>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-200">{isExec ? "All tickets" : "Your tickets"}</h2>
          <Button type="button" variant="outline" size="sm" className="border-zinc-700" onClick={() => void load()}>
            Refresh
          </Button>
        </div>
        {loading ? (
          <p className="py-8 text-center text-zinc-500">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-8 text-center text-sm text-zinc-500">No tickets yet.</p>
        ) : (
          <div className="space-y-3">
            {rows.map((t) => (
              <div key={t.id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-medium text-zinc-100">{t.subject}</div>
                    {isExec && (
                      <div className="mt-1 text-xs text-zinc-500">
                        From: {names[t.requester_id] ?? t.requester_id.slice(0, 8)}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {isExec ? (
                      <>
                        <select
                          className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
                          value={t.status}
                          onChange={(e) => void patchTicket(t.id, { status: e.target.value as CrmSupportTicketRow["status"] })}
                        >
                          {STATUSES.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                        <select
                          className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
                          value={t.priority}
                          onChange={(e) => void patchTicket(t.id, { priority: e.target.value as CrmSupportTicketRow["priority"] })}
                        >
                          {PRIOS.map((p) => (
                            <option key={p} value={p}>
                              {p}
                            </option>
                          ))}
                        </select>
                      </>
                    ) : (
                      <span className={cn("rounded px-2 py-1 text-xs", t.status === "open" ? "bg-amber-500/20 text-amber-200" : "bg-zinc-800 text-zinc-400")}>
                        {t.status} · {t.priority}
                      </span>
                    )}
                  </div>
                </div>
                {t.body ? <p className="mt-2 whitespace-pre-wrap text-zinc-400">{t.body}</p> : null}
                <div className="mt-2 text-[11px] text-zinc-600">
                  {new Date(t.created_at).toLocaleString()}
                  {t.updated_at !== t.created_at && <span> · updated {new Date(t.updated_at).toLocaleString()}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <p className="text-xs text-zinc-600">
        For product issues with the HAWK security app your clients use, track internal coordination here.{" "}
        <Link href="/crm/pipeline" className="text-emerald-400 hover:underline">
          Pipeline
        </Link>
      </p>
    </div>
  );
}
