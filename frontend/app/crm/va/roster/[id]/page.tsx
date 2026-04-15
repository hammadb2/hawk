"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import type { VaProfile, VaDailyReport, VaScore, VaCoachingNote } from "@/lib/crm/types";

export default function VaProfilePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const supabase = createClient();
  const { authReady, session, profile: myProfile } = useCrmAuth();
  const [va, setVa] = useState<VaProfile | null>(null);
  const [reports, setReports] = useState<VaDailyReport[]>([]);
  const [scores, setScores] = useState<VaScore[]>([]);
  const [notes, setNotes] = useState<VaCoachingNote[]>([]);
  const [loading, setLoading] = useState(true);

  /* coaching note form */
  const [noteText, setNoteText] = useState("");
  const [noteType, setNoteType] = useState<"coaching" | "pip" | "commendation">("coaching");
  const [saving, setSaving] = useState(false);

  /* deactivate confirmation */
  const [showDeactivateConfirm, setShowDeactivateConfirm] = useState(false);
  const [deactivating, setDeactivating] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    const [vpRes, drRes, scRes, cnRes] = await Promise.all([
      supabase.from("va_profiles").select("*").eq("id", id).maybeSingle(),
      supabase.from("va_daily_reports").select("*").eq("va_id", id).order("report_date", { ascending: false }).limit(30),
      supabase.from("va_scores").select("*").eq("va_id", id).order("week_start", { ascending: false }).limit(12),
      supabase.from("va_coaching_notes").select("*").eq("va_id", id).order("created_at", { ascending: false }).limit(50),
    ]);
    setVa((vpRes.data as VaProfile) ?? null);
    setReports((drRes.data ?? []) as VaDailyReport[]);
    setScores((scRes.data ?? []) as VaScore[]);
    setNotes((cnRes.data ?? []) as VaCoachingNote[]);
    setLoading(false);
  }, [id, supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  async function addNote() {
    if (!noteText.trim() || !myProfile || !id) return;
    setSaving(true);
    const { error } = await supabase.from("va_coaching_notes").insert({
      va_id: id,
      manager_id: myProfile.id,
      note: noteText.trim(),
      type: noteType,
    });
    if (error) {
      toast.error(error.message);
    } else {
      toast.success("Note saved");
      setNoteText("");
      void load();
    }
    setSaving(false);
  }

  async function updateStatus(newStatus: "active" | "pip") {
    if (!id) return;
    const { error } = await supabase.from("va_profiles").update({ status: newStatus }).eq("id", id);
    if (error) toast.error(error.message);
    else {
      toast.success(`Status updated to ${newStatus}`);
      void load();
    }
  }

  async function handleDeactivateVa() {
    if (!id || !session?.access_token) return;
    setDeactivating(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/va/deactivate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ va_id: id }),
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
      toast.success("VA deactivated — access revoked");
      setShowDeactivateConfirm(false);
      router.push("/crm/va/roster");
    } finally {
      setDeactivating(false);
    }
  }

  if (!authReady || !session || !myProfile || loading) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (!va) {
    return <p className="p-6 text-sm text-slate-600">VA not found.</p>;
  }

  const standingColor: Record<string, string> = {
    green: "bg-emerald-100 text-emerald-800",
    yellow: "bg-amber-100 text-amber-800",
    red: "bg-rose-100 text-rose-800",
  };

  const noteTypeColor: Record<string, string> = {
    coaching: "bg-sky-100 text-sky-800",
    pip: "bg-rose-100 text-rose-800",
    commendation: "bg-emerald-100 text-emerald-800",
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Link href="/crm/va/roster" className="text-sm text-emerald-600 hover:underline">
        ← Back to roster
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{va.full_name}</h1>
          <p className="text-sm text-slate-600">
            {va.email} · {va.role === "list_qa" ? "List QA" : "Reply & Book"} · Started {va.start_date}
          </p>
          <span
            className={`mt-1 inline-block rounded px-2 py-0.5 text-xs font-medium ${
              va.status === "active"
                ? "bg-emerald-100 text-emerald-800"
                : va.status === "pip"
                  ? "bg-amber-100 text-amber-800"
                  : "bg-slate-100 text-slate-600"
            }`}
          >
            {va.status.toUpperCase()}
          </span>
        </div>
        <div className="flex gap-2">
          {va.status !== "active" && va.status !== "inactive" && (
            <button type="button" className="rounded-lg border border-emerald-600 px-3 py-1 text-xs text-emerald-600 hover:bg-emerald-50" onClick={() => void updateStatus("active")}>
              Set Active
            </button>
          )}
          {va.status !== "pip" && va.status !== "inactive" && (
            <button type="button" className="rounded-lg border border-amber-500 px-3 py-1 text-xs text-amber-600 hover:bg-amber-50" onClick={() => void updateStatus("pip")}>
              Put on PIP
            </button>
          )}
          {va.status !== "inactive" && (
            <button type="button" className="rounded-lg border border-rose-300 px-3 py-1 text-xs text-rose-600 hover:bg-rose-50" onClick={() => setShowDeactivateConfirm(true)}>
              Deactivate VA
            </button>
          )}
        </div>
      </div>

      {/* Deactivate confirmation modal */}
      {showDeactivateConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-900">Deactivate {va.full_name}?</h3>
            <p className="mt-2 text-sm text-slate-600">
              This will set their status to inactive and revoke their login access. Historical data (daily reports, scores) will be preserved. This action cannot be easily undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                onClick={() => setShowDeactivateConfirm(false)}
                disabled={deactivating}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
                onClick={() => void handleDeactivateVa()}
                disabled={deactivating}
              >
                {deactivating ? "Deactivating\u2026" : "Deactivate"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Score history */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">Score History</h2>
        {scores.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No scores yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-600">
                <tr>
                  <th className="px-2 py-1">Week</th>
                  <th className="px-2 py-1">Output</th>
                  <th className="px-2 py-1">Accuracy</th>
                  <th className="px-2 py-1">Reply Ql</th>
                  <th className="px-2 py-1">Booking</th>
                  <th className="px-2 py-1">Total</th>
                  <th className="px-2 py-1">Standing</th>
                </tr>
              </thead>
              <tbody>
                {scores.map((s) => (
                  <tr key={s.id} className="border-b border-slate-100">
                    <td className="px-2 py-1 text-slate-600">{s.week_start}</td>
                    <td className="px-2 py-1">{s.output_score}</td>
                    <td className="px-2 py-1">{s.accuracy_score}</td>
                    <td className="px-2 py-1">{s.reply_quality_score}</td>
                    <td className="px-2 py-1">{s.booking_score}</td>
                    <td className="px-2 py-1 font-medium">{s.total_score}</td>
                    <td className="px-2 py-1">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${standingColor[s.standing] ?? ""}`}>
                        {s.standing.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent daily reports */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">Daily Reports (last 30)</h2>
        {reports.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No reports submitted yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-600">
                <tr>
                  <th className="px-2 py-1">Date</th>
                  <th className="px-2 py-1">Emails</th>
                  <th className="px-2 py-1">Replies</th>
                  <th className="px-2 py-1">Positive</th>
                  <th className="px-2 py-1">Calls</th>
                  <th className="px-2 py-1">No-shows</th>
                  <th className="px-2 py-1">Domains</th>
                  <th className="px-2 py-1">Blockers</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100">
                    <td className="px-2 py-1 text-slate-600">{r.report_date}</td>
                    <td className="px-2 py-1">{r.emails_sent}</td>
                    <td className="px-2 py-1">{r.replies_received}</td>
                    <td className="px-2 py-1">{r.positive_replies}</td>
                    <td className="px-2 py-1">{r.calls_booked}</td>
                    <td className="px-2 py-1">{r.no_shows}</td>
                    <td className="px-2 py-1">{r.domains_scanned}</td>
                    <td className="px-2 py-1 text-slate-500 max-w-[200px] truncate">{r.blockers || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Coaching notes */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-4">
        <h2 className="text-sm font-semibold text-slate-800">Coaching Log</h2>
        <div className="space-y-2">
          <textarea
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
            placeholder="Add a coaching note…"
            rows={3}
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
          />
          <div className="flex gap-2">
            <select
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              value={noteType}
              onChange={(e) => setNoteType(e.target.value as "coaching" | "pip" | "commendation")}
            >
              <option value="coaching">Coaching</option>
              <option value="pip">PIP</option>
              <option value="commendation">Commendation</option>
            </select>
            <button
              type="button"
              disabled={saving || !noteText.trim()}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              onClick={() => void addNote()}
            >
              {saving ? "Saving…" : "Save Note"}
            </button>
          </div>
        </div>
        {notes.length === 0 ? (
          <p className="text-sm text-slate-500">No coaching notes yet.</p>
        ) : (
          <ul className="space-y-2">
            {notes.map((n) => (
              <li key={n.id} className="rounded-lg border border-slate-200 px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${noteTypeColor[n.type] ?? ""}`}>
                    {n.type}
                  </span>
                  <span className="text-xs text-slate-500">{new Date(n.created_at).toLocaleString()}</span>
                </div>
                <p className="mt-1 text-sm text-slate-700">{n.note}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
