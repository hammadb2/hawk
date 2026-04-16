"use client";

import { useState } from "react";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface Props {
  accessToken: string;
  onRunStarted: (runId: string, vertical: string, location: string) => void;
}

const VERTICALS = [
  { value: "dental", label: "Dental Clinics" },
  { value: "legal", label: "Law Firms" },
  { value: "accounting", label: "Accounting Practices" },
];

export function PipelineRunTrigger({ accessToken, onRunStarted }: Props) {
  const [vertical, setVertical] = useState("dental");
  const [location, setLocation] = useState("Canada");
  const [batchSize, setBatchSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function triggerRun() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/aria/pipeline/run`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ vertical, location, batch_size: batchSize }),
      });
      if (r.ok) {
        const data = await r.json();
        onRunStarted(data.run_id, vertical, location);
      } else {
        const err = await r.json().catch(() => ({ detail: "Failed to start pipeline" }));
        setError(err.detail || "Failed to start pipeline");
      }
    } catch {
      setError("Connection error. Please try again.");
    }
    setLoading(false);
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">Run Outbound Pipeline</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Vertical</label>
          <select
            value={vertical}
            onChange={(e) => setVertical(e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-emerald-400 focus:outline-none"
          >
            {VERTICALS.map((v) => (
              <option key={v.value} value={v.value}>{v.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Location</label>
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Ontario, Canada"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-emerald-400 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Batch Size</label>
          <input
            type="number"
            value={batchSize}
            onChange={(e) => setBatchSize(Math.max(1, Math.min(500, parseInt(e.target.value) || 50)))}
            min={1}
            max={500}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-emerald-400 focus:outline-none"
          />
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <button
        onClick={() => void triggerRun()}
        disabled={loading || !location.trim()}
        className="mt-3 w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 transition"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Starting pipeline...
          </span>
        ) : (
          "Run Pipeline"
        )}
      </button>
    </div>
  );
}
