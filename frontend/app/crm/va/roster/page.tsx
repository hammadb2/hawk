"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import type { VaProfile, VaScore, VaAlert } from "@/lib/crm/types";

export default function VaRosterPage() {
  const supabase = createClient();
  const { authReady, session, profile } = useCrmAuth();
  const [vas, setVas] = useState<VaProfile[]>([]);
  const [scores, setScores] = useState<Record<string, VaScore>>({});
  const [alerts, setAlerts] = useState<VaAlert[]>([]);
  const [loading, setLoading] = useState(true);

  /* invite form */
  const [showInvite, setShowInvite] = useState(false);
  const [invFullName, setInvFullName] = useState("");
  const [invEmail, setInvEmail] = useState("");
  const [invRole, setInvRole] = useState<"list_qa" | "reply_book">("reply_book");
  const [inviting, setInviting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [vpRes, scRes, alRes] = await Promise.all([
      supabase.from("va_profiles").select("*").order("full_name"),
      supabase.from("va_scores").select("*").order("week_start", { ascending: false }),
      supabase.from("va_alerts").select("*").eq("acknowledged", false).order("created_at", { ascending: false }).limit(50),
    ]);
    setVas((vpRes.data ?? []) as VaProfile[]);
    /* latest score per VA */
    const sMap: Record<string, VaScore> = {};
    for (const s of (scRes.data ?? []) as VaScore[]) {
      if (!sMap[s.va_id]) sMap[s.va_id] = s;
    }
    setScores(sMap);
    setAlerts((alRes.data ?? []) as VaAlert[]);
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  async function handleInvite() {
    if (!invFullName.trim() || !invEmail.trim()) {
      toast.error("Name and email required");
      return;
    }
    if (!session?.access_token) {
      toast.error("Not signed in");
      return;
    }
    setInviting(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/invite`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          email: invEmail.trim(),
          full_name: invFullName.trim(),
          role: "va",
          va_sub_role: invRole,
        }),
      });
      if (!r.ok) {
        let msg = (await r.text()).slice(0, 240);
        try {
          const j = JSON.parse(msg) as { detail?: string };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          /* plain text */
        }
        toast.error(msg);
        return;
      }
      const j = (await r.json()) as { message?: string; existing_user?: boolean };
      toast.success(j.message || (j.existing_user ? "VA linked — check email for magic link." : "VA invite sent"));
      setInvFullName("");
      setInvEmail("");
      setShowInvite(false);
      void load();
    } finally {
      setInviting(false);
    }
  }

  async function ackAlert(id: string) {
    await supabase.from("va_alerts").update({ acknowledged: true }).eq("id", id);
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  const standingColor: Record<string, string> = {
    green: "text-emerald-600",
    yellow: "text-amber-500",
    red: "text-rose-600",
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">VA Team</h1>
          <p className="mt-1 text-sm text-slate-600">Roster, weekly scores, and alerts.</p>
        </div>
        <button
          type="button"
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          onClick={() => setShowInvite(!showInvite)}
        >
          {showInvite ? "Cancel" : "+ Invite VA"}
        </button>
      </div>

      {showInvite && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
          <h3 className="text-sm font-medium text-slate-800">Invite VA</h3>
          <div className="grid gap-3 sm:grid-cols-3">
            <input
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              placeholder="Full name"
              value={invFullName}
              onChange={(e) => setInvFullName(e.target.value)}
            />
            <input
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              placeholder="Email"
              type="email"
              value={invEmail}
              onChange={(e) => setInvEmail(e.target.value)}
            />
            <select
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              value={invRole}
              onChange={(e) => setInvRole(e.target.value as "list_qa" | "reply_book")}
            >
              <option value="reply_book">Reply &amp; Book</option>
              <option value="list_qa">List QA</option>
            </select>
          </div>
          <button
            type="button"
            disabled={inviting}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => void handleInvite()}
          >
            {inviting ? "Sending…" : "Send Invite"}
          </button>
        </div>
      )}

      {/* Active alerts */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-rose-700">Active Alerts ({alerts.length})</h2>
          {alerts.map((a) => (
            <div key={a.id} className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm">
              <span className="text-rose-800">{a.message}</span>
              <button
                type="button"
                className="ml-2 text-xs text-rose-600 underline hover:text-rose-800"
                onClick={() => void ackAlert(a.id)}
              >
                Dismiss
              </button>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12 text-slate-600">Loading…</div>
      ) : vas.length === 0 ? (
        <p className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-600">
          No VAs on the roster yet. Click &quot;+ Add VA&quot; to get started.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Score</th>
                <th className="px-3 py-2">Standing</th>
                <th className="px-3 py-2">Start</th>
              </tr>
            </thead>
            <tbody>
              {vas.map((va) => {
                const sc = scores[va.id];
                return (
                  <tr key={va.id} className="border-b border-slate-200/90 hover:bg-white">
                    <td className="px-3 py-2">
                      <Link href={`/crm/va/roster/${va.id}`} className="text-emerald-600 hover:underline font-medium">
                        {va.full_name}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{va.email}</td>
                    <td className="px-3 py-2 text-slate-700">{va.role === "list_qa" ? "List QA" : "Reply & Book"}</td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          va.status === "active"
                            ? "text-emerald-600"
                            : va.status === "pip"
                              ? "text-amber-500"
                              : "text-slate-400"
                        }
                      >
                        {va.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-700 font-medium">{sc?.total_score ?? "—"}</td>
                    <td className="px-3 py-2">
                      {sc ? (
                        <span className={`font-medium ${standingColor[sc.standing] ?? "text-slate-600"}`}>
                          {sc.standing.toUpperCase()}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{va.start_date}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
