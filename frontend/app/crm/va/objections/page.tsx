"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { Objection, AbTestVertical, ObjectionOutcome } from "@/lib/crm/types";

export default function ObjectionBankPage() {
  const supabase = createClient();
  const { authReady, session, profile } = useCrmAuth();
  const [objections, setObjections] = useState<Objection[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterVertical, setFilterVertical] = useState<string>("all");
  const [filterOutcome, setFilterOutcome] = useState<string>("all");

  /* form */
  const [showForm, setShowForm] = useState(false);
  const [objText, setObjText] = useState("");
  const [respUsed, setRespUsed] = useState("");
  const [outcome, setOutcome] = useState<ObjectionOutcome>("not_interested");
  const [vertical, setVertical] = useState<AbTestVertical>("dental");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase.from("objections").select("*").order("created_at", { ascending: false });
    setObjections((data ?? []) as Objection[]);
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  async function handleAdd() {
    if (!objText.trim()) {
      toast.error("Objection text required");
      return;
    }
    setSaving(true);
    const { error } = await supabase.from("objections").insert({
      objection_text: objText.trim(),
      response_used: respUsed.trim(),
      outcome,
      vertical,
    });
    if (error) toast.error(error.message);
    else {
      toast.success("Objection logged");
      setObjText("");
      setRespUsed("");
      setShowForm(false);
      void load();
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

  const filtered = objections.filter((o) => {
    if (filterVertical !== "all" && o.vertical !== filterVertical) return false;
    if (filterOutcome !== "all" && o.outcome !== filterOutcome) return false;
    return true;
  });

  const outcomeColor: Record<string, string> = {
    booked: "bg-emerald-100 text-emerald-800",
    warm: "bg-amber-100 text-amber-800",
    not_interested: "bg-slate-100 text-slate-600",
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Objection Bank</h1>
          <p className="mt-1 text-sm text-slate-600">Log objections, responses, and outcomes across verticals.</p>
        </div>
        <button
          type="button"
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? "Cancel" : "+ Log Objection"}
        </button>
      </div>

      {showForm && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
          <textarea
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
            placeholder="What did they say?"
            rows={2}
            value={objText}
            onChange={(e) => setObjText(e.target.value)}
          />
          <textarea
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
            placeholder="How did you respond?"
            rows={2}
            value={respUsed}
            onChange={(e) => setRespUsed(e.target.value)}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <select
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              value={vertical}
              onChange={(e) => setVertical(e.target.value as AbTestVertical)}
            >
              <option value="dental">Dental</option>
              <option value="legal">Legal</option>
              <option value="accounting">Accounting</option>
            </select>
            <select
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as ObjectionOutcome)}
            >
              <option value="booked">Booked</option>
              <option value="warm">Warm</option>
              <option value="not_interested">Not Interested</option>
            </select>
          </div>
          <button
            type="button"
            disabled={saving}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => void handleAdd()}
          >
            {saving ? "Saving…" : "Save Objection"}
          </button>
        </div>
      )}

      <div className="flex gap-2">
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
        <select
          className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
          value={filterOutcome}
          onChange={(e) => setFilterOutcome(e.target.value)}
        >
          <option value="all">All outcomes</option>
          <option value="booked">Booked</option>
          <option value="warm">Warm</option>
          <option value="not_interested">Not Interested</option>
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-12 text-slate-600">Loading…</div>
      ) : filtered.length === 0 ? (
        <p className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-600">
          No objections logged yet.
        </p>
      ) : (
        <div className="space-y-3">
          {filtered.map((o) => (
            <div key={o.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${outcomeColor[o.outcome] ?? ""}`}>
                  {o.outcome.replace("_", " ")}
                </span>
                <span className="text-xs text-slate-500 capitalize">{o.vertical}</span>
                <span className="text-xs text-slate-400">{new Date(o.created_at).toLocaleDateString()}</span>
              </div>
              <p className="text-sm font-medium text-slate-800">&ldquo;{o.objection_text}&rdquo;</p>
              {o.response_used && (
                <p className="mt-1 text-sm text-slate-600">
                  <span className="font-medium text-slate-700">Response:</span> {o.response_used}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
