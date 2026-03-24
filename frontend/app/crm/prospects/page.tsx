"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { crmProspectsApi } from "@/lib/crm-api";
import { StageBadge } from "@/components/crm/stage-badge";
import { HawkScoreBadge } from "@/components/crm/hawk-score-badge";
import type { Prospect, PipelineStage } from "@/lib/crm-types";
import { PIPELINE_STAGES, STAGE_LABELS } from "@/lib/crm-types";

function AddProspectModal({ onClose, onCreated }: { onClose: () => void; onCreated: (p: Prospect) => void }) {
  const { token } = useAuth();
  const [form, setForm] = useState({ company_name: "", domain: "", contact_name: "", contact_email: "", contact_phone: "", industry: "", city: "" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !form.company_name.trim()) return setError("Company name is required");
    setSaving(true);
    try {
      const p = await crmProspectsApi.create(token, { ...form, domain: form.domain || undefined });
      onCreated(p);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl">
        <h2 className="font-semibold text-lg mb-4">Add Prospect</h2>
        <form onSubmit={submit} className="flex flex-col gap-3">
          {[
            { key: "company_name", label: "Company Name *" },
            { key: "domain", label: "Domain" },
            { key: "contact_name", label: "Contact Name" },
            { key: "contact_email", label: "Contact Email" },
            { key: "contact_phone", label: "Phone" },
            { key: "industry", label: "Industry" },
            { key: "city", label: "City" },
          ].map(({ key, label }) => (
            <div key={key}>
              <label className="text-xs text-text-secondary block mb-1">{label}</label>
              <input
                value={(form as any)[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                className="w-full border border-surface-3 rounded px-3 py-2 text-sm"
              />
            </div>
          ))}
          {error && <p className="text-red-500 text-xs">{error}</p>}
          <div className="flex gap-2 justify-end mt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50">
              {saving ? "Adding…" : "Add Prospect"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ProspectsPage() {
  const { token } = useAuth();
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [csvError, setCsvError] = useState("");
  const [csvMsg, setCsvMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    if (!token) return;
    try {
      const data = await crmProspectsApi.list(token, { search: search || undefined, stage: stageFilter || undefined, limit: 200 });
      setProspects(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [token, search, stageFilter]);

  const handleCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !token) return;
    setCsvError(""); setCsvMsg("");
    try {
      const res = await crmProspectsApi.importCSV(token, file);
      setCsvMsg(`Imported ${res.created} prospects. Skipped ${res.skipped} duplicates.`);
      load();
    } catch (err: any) {
      setCsvError(err.message);
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Prospects</h1>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="border border-surface-3 rounded px-3 py-1.5 text-sm w-44"
          />
          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="border border-surface-3 rounded px-2 py-1.5 text-sm"
          >
            <option value="">All Stages</option>
            {PIPELINE_STAGES.map((s) => (
              <option key={s} value={s}>{STAGE_LABELS[s]}</option>
            ))}
          </select>
          <label className="bg-white border border-surface-3 text-text-secondary px-3 py-1.5 rounded text-sm cursor-pointer hover:bg-surface-2">
            Import CSV
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleCSV} />
          </label>
          <button onClick={() => setShowAdd(true)} className="bg-purple-600 text-white px-4 py-1.5 rounded text-sm hover:bg-purple-700">
            + Add Prospect
          </button>
        </div>
      </div>

      {csvMsg && <p className="text-green-600 text-sm mb-3">{csvMsg}</p>}
      {csvError && <p className="text-red-500 text-sm mb-3">{csvError}</p>}

      <div className="bg-white border border-surface-3 rounded-lg overflow-hidden">
        <div className="px-4 py-2 border-b border-surface-3 bg-surface-2 text-xs text-text-secondary">
          {loading ? "Loading…" : `${prospects.length} prospects`}
        </div>
        <table className="w-full text-sm">
          <thead className="border-b border-surface-3">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Company</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Stage</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Score</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Contact</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Rep</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Source</th>
            </tr>
          </thead>
          <tbody>
            {prospects.map((p) => (
              <tr key={p.id} className="border-b border-surface-3 last:border-0 hover:bg-surface-2">
                <td className="px-4 py-2.5">
                  <Link href={`/crm/prospects/${p.id}`} className="font-medium hover:text-purple-600">{p.company_name}</Link>
                  {p.domain && <p className="text-xs text-text-secondary">{p.domain}</p>}
                </td>
                <td className="px-4 py-2.5"><StageBadge stage={p.stage} /></td>
                <td className="px-4 py-2.5"><HawkScoreBadge score={p.hawk_score} /></td>
                <td className="px-4 py-2.5 text-xs text-text-secondary">
                  {p.contact_name && <p>{p.contact_name}</p>}
                  {p.contact_email && <p>{p.contact_email}</p>}
                </td>
                <td className="px-4 py-2.5 text-xs text-text-secondary">{p.assigned_rep_name || "—"}</td>
                <td className="px-4 py-2.5 text-xs text-text-secondary capitalize">{p.source}</td>
              </tr>
            ))}
            {!loading && prospects.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-text-secondary">No prospects yet. Add one or import a CSV.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <AddProspectModal
          onClose={() => setShowAdd(false)}
          onCreated={(p) => { setProspects((prev) => [p, ...prev]); setShowAdd(false); }}
        />
      )}
    </div>
  );
}
