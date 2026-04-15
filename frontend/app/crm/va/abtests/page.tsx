"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { AbTest, AbTestVertical } from "@/lib/crm/types";

export default function AbTestsPage() {
  const supabase = createClient();
  const { authReady, session, profile } = useCrmAuth();
  const [tests, setTests] = useState<AbTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterVertical, setFilterVertical] = useState<string>("all");

  /* new test form */
  const [showForm, setShowForm] = useState(false);
  const [subjectLine, setSubjectLine] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [vertical, setVertical] = useState<AbTestVertical>("dental");
  const [sends, setSends] = useState(0);
  const [openRate, setOpenRate] = useState(0);
  const [replyRate, setReplyRate] = useState(0);
  const [bookRate, setBookRate] = useState(0);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase.from("ab_tests").select("*").order("created_at", { ascending: false });
    setTests((data ?? []) as AbTest[]);
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  async function handleAdd() {
    if (!subjectLine.trim()) {
      toast.error("Subject line required");
      return;
    }
    setSaving(true);
    const { error } = await supabase.from("ab_tests").insert({
      subject_line: subjectLine.trim(),
      email_body: emailBody.trim(),
      vertical,
      sends,
      open_rate: openRate,
      reply_rate: replyRate,
      book_rate: bookRate,
      winner: false,
    });
    if (error) toast.error(error.message);
    else {
      toast.success("A/B test logged");
      setSubjectLine("");
      setEmailBody("");
      setSends(0);
      setOpenRate(0);
      setReplyRate(0);
      setBookRate(0);
      setShowForm(false);
      void load();
    }
    setSaving(false);
  }

  async function toggleWinner(id: string, current: boolean) {
    const { error } = await supabase.from("ab_tests").update({ winner: !current }).eq("id", id);
    if (error) toast.error(error.message);
    else void load();
  }

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  const filtered = filterVertical === "all" ? tests : tests.filter((t) => t.vertical === filterVertical);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">A/B Tests</h1>
          <p className="mt-1 text-sm text-slate-600">Track subject lines, bodies, and performance across verticals.</p>
        </div>
        <button
          type="button"
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? "Cancel" : "+ Log Test"}
        </button>
      </div>

      {showForm && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              placeholder="Subject line"
              value={subjectLine}
              onChange={(e) => setSubjectLine(e.target.value)}
            />
            <select
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              value={vertical}
              onChange={(e) => setVertical(e.target.value as AbTestVertical)}
            >
              <option value="dental">Dental</option>
              <option value="legal">Legal</option>
              <option value="accounting">Accounting</option>
            </select>
          </div>
          <textarea
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
            placeholder="Email body (optional)"
            rows={3}
            value={emailBody}
            onChange={(e) => setEmailBody(e.target.value)}
          />
          <div className="grid gap-3 sm:grid-cols-4">
            <div>
              <label className="block text-xs text-slate-600 mb-1">Sends</label>
              <input type="number" min={0} className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800" value={sends} onChange={(e) => setSends(parseInt(e.target.value, 10) || 0)} />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Open Rate (%)</label>
              <input type="number" min={0} step={0.1} className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800" value={openRate} onChange={(e) => setOpenRate(parseFloat(e.target.value) || 0)} />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Reply Rate (%)</label>
              <input type="number" min={0} step={0.1} className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800" value={replyRate} onChange={(e) => setReplyRate(parseFloat(e.target.value) || 0)} />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Book Rate (%)</label>
              <input type="number" min={0} step={0.1} className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800" value={bookRate} onChange={(e) => setBookRate(parseFloat(e.target.value) || 0)} />
            </div>
          </div>
          <button
            type="button"
            disabled={saving}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => void handleAdd()}
          >
            {saving ? "Saving…" : "Save Test"}
          </button>
        </div>
      )}

      <div>
        <select
          className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
          value={filterVertical}
          onChange={(e) => setFilterVertical(e.target.value)}
        >
          <option value="all">All verticals</option>
          <option value="dental">Dental</option>
          <option value="legal">Legal</option>
          <option value="accounting">Accounting</option>
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-12 text-slate-600">Loading…</div>
      ) : filtered.length === 0 ? (
        <p className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-600">
          No A/B tests logged yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Subject</th>
                <th className="px-3 py-2">Vertical</th>
                <th className="px-3 py-2">Sends</th>
                <th className="px-3 py-2">Open %</th>
                <th className="px-3 py-2">Reply %</th>
                <th className="px-3 py-2">Book %</th>
                <th className="px-3 py-2">Winner</th>
                <th className="px-3 py-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.id} className="border-b border-slate-200/90 hover:bg-white">
                  <td className="px-3 py-2 text-slate-800 max-w-[250px] truncate" title={t.subject_line}>
                    {t.subject_line}
                  </td>
                  <td className="px-3 py-2 text-slate-600 capitalize">{t.vertical}</td>
                  <td className="px-3 py-2">{t.sends}</td>
                  <td className="px-3 py-2">{t.open_rate.toFixed(1)}%</td>
                  <td className="px-3 py-2">{t.reply_rate.toFixed(1)}%</td>
                  <td className="px-3 py-2">{t.book_rate.toFixed(1)}%</td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      className={`rounded px-2 py-0.5 text-xs font-medium ${t.winner ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-500"}`}
                      onClick={() => void toggleWinner(t.id, t.winner)}
                    >
                      {t.winner ? "WINNER" : "—"}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
