"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { VaProfile, VaDailyReport } from "@/lib/crm/types";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function VaDailyInputPage() {
  const supabase = createClient();
  const { authReady, session, profile } = useCrmAuth();
  const [vaProfile, setVaProfile] = useState<VaProfile | null>(null);
  const [allVas, setAllVas] = useState<VaProfile[]>([]);
  const [selectedVaId, setSelectedVaId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [todayReport, setTodayReport] = useState<VaDailyReport | null>(null);
  const [recentReports, setRecentReports] = useState<VaDailyReport[]>([]);

  /* form */
  const [emailsSent, setEmailsSent] = useState(0);
  const [repliesReceived, setRepliesReceived] = useState(0);
  const [positiveReplies, setPositiveReplies] = useState(0);
  const [callsBooked, setCallsBooked] = useState(0);
  const [noShows, setNoShows] = useState(0);
  const [domainsScanned, setDomainsScanned] = useState(0);
  const [blockers, setBlockers] = useState("");

  const isManager = profile?.role === "ceo" || profile?.role === "hos" || profile?.role === "va_manager" || profile?.role === "team_lead";

  const load = useCallback(async () => {
    setLoading(true);
    const today = todayIso();

    if (isManager) {
      const { data: vaList } = await supabase.from("va_profiles").select("*").eq("status", "active").order("full_name");
      setAllVas((vaList ?? []) as VaProfile[]);
    }

    /* find the VA profile for the current user */
    const { data: myVa } = await supabase
      .from("va_profiles")
      .select("*")
      .eq("user_id", session?.user?.id ?? "")
      .maybeSingle();
    const vp = myVa as VaProfile | null;
    setVaProfile(vp);

    const targetVaId = vp?.id || selectedVaId;
    if (targetVaId) {
      const [trRes, rrRes] = await Promise.all([
        supabase.from("va_daily_reports").select("*").eq("va_id", targetVaId).eq("report_date", today).maybeSingle(),
        supabase.from("va_daily_reports").select("*").eq("va_id", targetVaId).order("report_date", { ascending: false }).limit(7),
      ]);
      const existing = trRes.data as VaDailyReport | null;
      setTodayReport(existing);
      setRecentReports((rrRes.data ?? []) as VaDailyReport[]);
      if (existing) {
        setEmailsSent(existing.emails_sent);
        setRepliesReceived(existing.replies_received);
        setPositiveReplies(existing.positive_replies);
        setCallsBooked(existing.calls_booked);
        setNoShows(existing.no_shows);
        setDomainsScanned(existing.domains_scanned);
        setBlockers(existing.blockers ?? "");
      }
    }
    setLoading(false);
  }, [supabase, session?.user?.id, isManager, selectedVaId]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  async function handleSubmit() {
    const targetVaId = vaProfile?.id || selectedVaId;
    if (!targetVaId) {
      toast.error("No VA profile found for your account");
      return;
    }
    setSaving(true);
    const payload = {
      va_id: targetVaId,
      report_date: todayIso(),
      emails_sent: emailsSent,
      replies_received: repliesReceived,
      positive_replies: positiveReplies,
      calls_booked: callsBooked,
      no_shows: noShows,
      domains_scanned: domainsScanned,
      blockers: blockers.trim() || null,
    };
    if (todayReport) {
      const { error } = await supabase.from("va_daily_reports").update(payload).eq("id", todayReport.id);
      if (error) toast.error(error.message);
      else {
        toast.success("Report updated");
        void load();
      }
    } else {
      const { error } = await supabase.from("va_daily_reports").insert(payload);
      if (error) toast.error(error.message);
      else {
        toast.success("Report submitted");
        void load();
      }
    }
    setSaving(false);
  }

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (loading) {
    return <div className="flex justify-center py-12 text-slate-600">Loading…</div>;
  }

  const effectiveVaId = vaProfile?.id || selectedVaId;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">VA Daily Input</h1>
        <p className="mt-1 text-sm text-slate-600">
          {todayReport ? `Editing today's report (${todayIso()})` : `Submit your numbers for ${todayIso()}`}
        </p>
      </div>

      {/* Manager VA selector */}
      {isManager && !vaProfile && allVas.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Select VA</label>
          <select
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 w-full"
            value={selectedVaId}
            onChange={(e) => setSelectedVaId(e.target.value)}
          >
            <option value="">Choose a VA…</option>
            {allVas.map((v) => (
              <option key={v.id} value={v.id}>{v.full_name} ({v.email})</option>
            ))}
          </select>
        </div>
      )}

      {!vaProfile && !isManager && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          No VA profile is linked to your account. Ask your manager to add you to the VA roster.
        </div>
      )}

      {(vaProfile || (isManager && effectiveVaId)) && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <NumberField label="Emails Sent" value={emailsSent} onChange={setEmailsSent} />
            <NumberField label="Replies Received" value={repliesReceived} onChange={setRepliesReceived} />
            <NumberField label="Positive Replies" value={positiveReplies} onChange={setPositiveReplies} />
            <NumberField label="Calls Booked" value={callsBooked} onChange={setCallsBooked} />
            <NumberField label="No-Shows" value={noShows} onChange={setNoShows} />
            <NumberField label="Domains Scanned" value={domainsScanned} onChange={setDomainsScanned} />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Blockers / Notes</label>
            <textarea
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              rows={3}
              value={blockers}
              onChange={(e) => setBlockers(e.target.value)}
              placeholder="Any blockers or notes for today…"
            />
          </div>
          <button
            type="button"
            disabled={saving}
            className="rounded-lg bg-emerald-600 px-6 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => void handleSubmit()}
          >
            {saving ? "Saving…" : todayReport ? "Update Report" : "Submit Report"}
          </button>
        </div>
      )}

      {/* Recent reports */}
      {recentReports.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-800 mb-3">Recent Reports</h2>
          <div className="overflow-x-auto">
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
                </tr>
              </thead>
              <tbody>
                {recentReports.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100">
                    <td className="px-2 py-1 text-slate-600">{r.report_date}</td>
                    <td className="px-2 py-1">{r.emails_sent}</td>
                    <td className="px-2 py-1">{r.replies_received}</td>
                    <td className="px-2 py-1">{r.positive_replies}</td>
                    <td className="px-2 py-1">{r.calls_booked}</td>
                    <td className="px-2 py-1">{r.no_shows}</td>
                    <td className="px-2 py-1">{r.domains_scanned}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      <input
        type="number"
        min={0}
        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
        value={value}
        onChange={(e) => onChange(Math.max(0, parseInt(e.target.value, 10) || 0))}
      />
    </div>
  );
}
