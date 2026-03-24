"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { useCRM } from "@/components/crm/crm-provider";
import { crmProspectsApi, crmActivitiesApi } from "@/lib/crm-api";
import { StageBadge } from "@/components/crm/stage-badge";
import { HawkScoreBadge } from "@/components/crm/hawk-score-badge";
import type { Prospect, Activity, PipelineStage } from "@/lib/crm-types";
import { PIPELINE_STAGES, STAGE_LABELS } from "@/lib/crm-types";

function ActivityIcon({ type }: { type: string }) {
  const icons: Record<string, string> = {
    call: "📞", email: "✉️", note: "📝", stage_change: "→", loom: "🎬", meeting: "📅",
  };
  return <span>{icons[type] || "·"}</span>;
}

export default function ProspectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const { hasFullVisibility } = useCRM();
  const router = useRouter();
  const [prospect, setProspect] = useState<Prospect | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [newNote, setNewNote] = useState("");
  const [selectedStage, setSelectedStage] = useState<PipelineStage | "">("");
  const [error, setError] = useState("");

  const load = async () => {
    if (!token || !id) return;
    try {
      const [p, acts] = await Promise.all([
        crmProspectsApi.get(token, id),
        crmActivitiesApi.listForProspect(token, id),
      ]);
      setProspect(p);
      setActivities(acts);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [token, id]);

  const addNote = async () => {
    if (!token || !newNote.trim() || !id) return;
    const a = await crmActivitiesApi.create(token, { prospect_id: id, activity_type: "note", description: newNote });
    setActivities((prev) => [a, ...prev]);
    setNewNote("");
  };

  const moveStage = async () => {
    if (!token || !selectedStage || !id) return;
    const updated = await crmProspectsApi.moveStage(token, id, selectedStage);
    setProspect(updated);
    const acts = await crmActivitiesApi.listForProspect(token, id);
    setActivities(acts);
    setSelectedStage("");
  };

  const convert = async () => {
    if (!token || !id) return;
    try {
      await crmProspectsApi.convert(token, id);
      router.push("/crm/clients");
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (loading) return <p className="text-text-secondary text-sm">Loading…</p>;
  if (error) return <p className="text-red-500 text-sm">{error}</p>;
  if (!prospect) return null;

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-2 mb-4">
        <Link href="/crm/prospects" className="text-text-secondary text-sm hover:text-purple-600">← Prospects</Link>
        <span className="text-text-secondary">/</span>
        <span className="text-sm">{prospect.company_name}</span>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Details */}
        <div className="col-span-2 flex flex-col gap-4">
          <div className="bg-white border border-surface-3 rounded-lg p-5">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h1 className="text-xl font-semibold">{prospect.company_name}</h1>
                {prospect.domain && <p className="text-sm text-text-secondary">{prospect.domain}</p>}
              </div>
              <div className="flex items-center gap-2">
                <HawkScoreBadge score={prospect.hawk_score} />
                <StageBadge stage={prospect.stage} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[
                ["Contact", prospect.contact_name],
                ["Email", prospect.contact_email],
                ["Phone", prospect.contact_phone],
                ["Industry", prospect.industry],
                ["City", prospect.city],
                ["Source", prospect.source],
                ["Rep", prospect.assigned_rep_name],
                ["MRR Estimate", prospect.estimated_mrr ? `$${(prospect.estimated_mrr / 100).toLocaleString()}` : null],
              ].map(([label, value]) =>
                value ? (
                  <div key={label as string}>
                    <p className="text-xs text-text-secondary">{label}</p>
                    <p>{value}</p>
                  </div>
                ) : null
              )}
            </div>
            {prospect.notes && (
              <div className="mt-3 pt-3 border-t border-surface-3">
                <p className="text-xs text-text-secondary mb-1">Notes</p>
                <p className="text-sm">{prospect.notes}</p>
              </div>
            )}
          </div>

          {/* Stage move */}
          <div className="bg-white border border-surface-3 rounded-lg p-4">
            <h2 className="font-medium text-sm mb-3">Move Stage</h2>
            <div className="flex gap-2">
              <select
                value={selectedStage}
                onChange={(e) => setSelectedStage(e.target.value as PipelineStage)}
                className="flex-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
              >
                <option value="">Select stage…</option>
                {PIPELINE_STAGES.filter((s) => s !== prospect.stage).map((s) => (
                  <option key={s} value={s}>{STAGE_LABELS[s]}</option>
                ))}
              </select>
              <button
                onClick={moveStage}
                disabled={!selectedStage}
                className="px-4 py-1.5 bg-purple-600 text-white text-sm rounded hover:bg-purple-700 disabled:opacity-40"
              >
                Move
              </button>
              {prospect.stage === "closed_won" && (
                <button
                  onClick={convert}
                  className="px-4 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                >
                  Convert to Client
                </button>
              )}
            </div>
          </div>

          {/* Log note */}
          <div className="bg-white border border-surface-3 rounded-lg p-4">
            <h2 className="font-medium text-sm mb-3">Log Activity</h2>
            <div className="flex gap-2">
              <input
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                placeholder="Add a note…"
                className="flex-1 border border-surface-3 rounded px-3 py-1.5 text-sm"
                onKeyDown={(e) => e.key === "Enter" && addNote()}
              />
              <button onClick={addNote} disabled={!newNote.trim()} className="px-4 py-1.5 bg-purple-600 text-white text-sm rounded hover:bg-purple-700 disabled:opacity-40">
                Save
              </button>
            </div>
          </div>

          {/* Activity timeline */}
          <div className="bg-white border border-surface-3 rounded-lg p-4">
            <h2 className="font-medium text-sm mb-3">Activity Timeline</h2>
            {activities.length === 0 ? (
              <p className="text-text-secondary text-sm">No activity yet.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {activities.map((a) => (
                  <div key={a.id} className="flex gap-3 text-sm">
                    <span className="w-5 shrink-0 text-center"><ActivityIcon type={a.activity_type} /></span>
                    <div className="flex-1">
                      {a.activity_type === "stage_change" ? (
                        <p className="text-text-secondary">
                          Stage changed: <span className="font-medium">{a.old_stage}</span> → <span className="font-medium">{a.new_stage}</span>
                        </p>
                      ) : (
                        <p>{a.description || <span className="text-text-secondary capitalize">{a.activity_type}</span>}</p>
                      )}
                      <p className="text-xs text-text-secondary mt-0.5">
                        {a.crm_user_name || "System"} · {new Date(a.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Quick info */}
        <div className="flex flex-col gap-4">
          <div className="bg-purple-50 border border-purple-100 rounded-lg p-4">
            <p className="text-xs text-purple-600 font-medium mb-2">HAWK Score</p>
            <div className="flex items-center gap-2">
              <HawkScoreBadge score={prospect.hawk_score} />
              <span className="text-xs text-text-secondary">
                {prospect.hawk_score === null ? "Not scanned yet" : prospect.hawk_score >= 70 ? "High risk" : prospect.hawk_score >= 40 ? "Medium risk" : "Low risk"}
              </span>
            </div>
          </div>
          <div className="bg-white border border-surface-3 rounded-lg p-4">
            <p className="text-xs text-text-secondary mb-1">Added</p>
            <p className="text-sm">{new Date(prospect.created_at).toLocaleDateString()}</p>
            <p className="text-xs text-text-secondary mb-1 mt-2">Last Updated</p>
            <p className="text-sm">{new Date(prospect.updated_at).toLocaleDateString()}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
