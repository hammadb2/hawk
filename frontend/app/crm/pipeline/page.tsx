"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { crmProspectsApi } from "@/lib/crm-api";
import { StageBadge } from "@/components/crm/stage-badge";
import { HawkScoreBadge } from "@/components/crm/hawk-score-badge";
import type { Prospect, PipelineStage } from "@/lib/crm-types";
import { PIPELINE_STAGES, STAGE_LABELS } from "@/lib/crm-types";

export default function PipelinePage() {
  const { token } = useAuth();
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"kanban" | "list">("kanban");
  const [search, setSearch] = useState("");

  const load = async () => {
    if (!token) return;
    try {
      const data = await crmProspectsApi.list(token, { limit: 200 });
      setProspects(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [token]);

  const filtered = prospects.filter(
    (p) => !search || p.company_name.toLowerCase().includes(search.toLowerCase()) || (p.domain || "").toLowerCase().includes(search.toLowerCase())
  );

  const byStage = (stage: PipelineStage) => filtered.filter((p) => p.stage === stage);

  const moveStage = async (prospectId: string, newStage: PipelineStage) => {
    if (!token) return;
    await crmProspectsApi.moveStage(token, prospectId, newStage);
    setProspects((prev) => prev.map((p) => p.id === prospectId ? { ...p, stage: newStage, updated_at: new Date().toISOString() } : p));
  };

  if (loading) return <p className="text-text-secondary text-sm">Loading pipeline…</p>;

  const activeStages = PIPELINE_STAGES.filter((s) => s !== "closed_won" && s !== "closed_lost");

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Pipeline</h1>
        <div className="flex items-center gap-3">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="border border-surface-3 rounded px-3 py-1.5 text-sm w-48"
          />
          <div className="flex border border-surface-3 rounded overflow-hidden">
            {(["kanban", "list"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1.5 text-sm capitalize ${view === v ? "bg-purple-600 text-white" : "text-text-secondary hover:bg-surface-2"}`}
              >
                {v}
              </button>
            ))}
          </div>
          <Link href="/crm/prospects" className="bg-purple-600 text-white px-4 py-1.5 rounded text-sm hover:bg-purple-700">
            + Add
          </Link>
        </div>
      </div>

      {view === "kanban" ? (
        <div className="flex gap-3 overflow-x-auto pb-4 flex-1">
          {activeStages.map((stage) => {
            const cards = byStage(stage);
            return (
              <div key={stage} className="min-w-[200px] max-w-[220px] flex flex-col">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-text-secondary uppercase tracking-wide">{STAGE_LABELS[stage]}</span>
                  <span className="text-xs text-text-secondary bg-surface-2 rounded-full px-1.5">{cards.length}</span>
                </div>
                <div className="flex flex-col gap-2 flex-1">
                  {cards.map((p) => (
                    <Link
                      key={p.id}
                      href={`/crm/prospects/${p.id}`}
                      className="bg-white border border-surface-3 rounded-lg p-3 hover:border-purple-300 transition-colors block"
                    >
                      <p className="text-sm font-medium text-text-primary leading-snug">{p.company_name}</p>
                      {p.domain && <p className="text-xs text-text-secondary mt-0.5">{p.domain}</p>}
                      <div className="flex items-center gap-1 mt-2">
                        <HawkScoreBadge score={p.hawk_score} />
                        {p.assigned_rep_name && (
                          <span className="text-xs text-text-secondary truncate">{p.assigned_rep_name.split(" ")[0]}</span>
                        )}
                      </div>
                    </Link>
                  ))}
                  {cards.length === 0 && (
                    <div className="border border-dashed border-surface-3 rounded-lg p-4 text-center">
                      <p className="text-xs text-text-secondary">Empty</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-white border border-surface-3 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 border-b border-surface-3">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Company</th>
                <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Stage</th>
                <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Score</th>
                <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Rep</th>
                <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p, i) => (
                <tr key={p.id} className={`border-b border-surface-3 last:border-0 hover:bg-surface-2 ${i % 2 === 0 ? "" : "bg-gray-50"}`}>
                  <td className="px-4 py-2.5">
                    <Link href={`/crm/prospects/${p.id}`} className="font-medium hover:text-purple-600">
                      {p.company_name}
                    </Link>
                    {p.domain && <p className="text-xs text-text-secondary">{p.domain}</p>}
                  </td>
                  <td className="px-4 py-2.5"><StageBadge stage={p.stage} /></td>
                  <td className="px-4 py-2.5"><HawkScoreBadge score={p.hawk_score} /></td>
                  <td className="px-4 py-2.5 text-text-secondary text-xs">{p.assigned_rep_name || "—"}</td>
                  <td className="px-4 py-2.5 text-text-secondary text-xs capitalize">{p.source}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-text-secondary text-sm">No prospects found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
