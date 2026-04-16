"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import Link from "next/link";

/* ── Types ────────────────────────────────────────────────────────────── */

interface ProspectInfo {
  id: string;
  company_name: string | null;
  domain: string | null;
  contact_name: string | null;
  contact_email: string | null;
  industry: string | null;
  hawk_score: number | null;
  stage: string | null;
}

interface InboundReply {
  id: string;
  prospect_id: string;
  reply_content: string;
  reply_subject: string | null;
  reply_from_email: string | null;
  reply_from_name: string | null;
  reply_received_at: string;
  classification: string;
  classification_confidence: number | null;
  classification_reasoning: string | null;
  draft_subject: string | null;
  draft_body: string | null;
  draft_reasoning: string | null;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  sent_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  prospects: ProspectInfo | null;
}

interface QueueStats {
  pending_review: number;
  approved: number;
  sent: number;
  rejected: number;
  auto_handled: number;
}

/* ── Helpers ──────────────────────────────────────────────────────────── */

const CLASSIFICATION_LABELS: Record<string, { label: string; color: string }> = {
  interested: { label: "Interested", color: "bg-emerald-100 text-emerald-800" },
  objection: { label: "Objection", color: "bg-amber-100 text-amber-800" },
  not_interested: { label: "Not Interested", color: "bg-rose-100 text-rose-800" },
  unsubscribe: { label: "Unsubscribe", color: "bg-slate-100 text-slate-800" },
  out_of_office: { label: "Out of Office", color: "bg-blue-100 text-blue-800" },
  question: { label: "Question", color: "bg-violet-100 text-violet-800" },
  positive_other: { label: "Positive", color: "bg-teal-100 text-teal-800" },
  pending: { label: "Pending", color: "bg-gray-100 text-gray-600" },
};

const STATUS_TABS: { key: string; label: string }[] = [
  { key: "pending_review", label: "Pending Review" },
  { key: "approved", label: "Approved" },
  { key: "sent", label: "Sent" },
  { key: "rejected", label: "Rejected" },
  { key: "auto_handled", label: "Auto-handled" },
];

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

/* ── Component ────────────────────────────────────────────────────────── */

export default function AriaRepliesPage() {
  const supabase = useMemo(() => createClient(), []);
  const { profile, session } = useCrmAuth();
  const [replies, setReplies] = useState<InboundReply[]>([]);
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [activeTab, setActiveTab] = useState("pending_review");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const headers = useMemo((): Record<string, string> => {
    if (!session?.access_token) return {};
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
    };
  }, [session?.access_token]);

  /* ── Data loading ─────────────────────────────────────────────────── */

  const loadReplies = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(
        `${CRM_API_BASE_URL}/api/crm/ai/replies/pending?status=${activeTab}&limit=50`,
        { headers }
      );
      if (!r.ok) {
        const text = await r.text();
        setErr(text || "Failed to load replies");
        setReplies([]);
      } else {
        const data = await r.json();
        setReplies(data.replies || []);
      }
    } catch (e) {
      setErr("Network error loading replies");
    }
    setLoading(false);
  }, [session?.access_token, activeTab, headers]);

  const loadStats = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/replies/stats`, { headers });
      if (r.ok) {
        const data = await r.json();
        setStats(data.stats || null);
      }
    } catch {
      // stats are non-critical
    }
  }, [session?.access_token, headers]);

  useEffect(() => {
    void loadReplies();
    void loadStats();
  }, [loadReplies, loadStats]);

  /* ── Actions ──────────────────────────────────────────────────────── */

  async function approveReply(replyId: string, editedBody?: string) {
    setBusy(replyId);
    setErr(null);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/replies/${replyId}/approve`, {
        method: "POST",
        headers,
        body: JSON.stringify({ edited_body: editedBody || null }),
      });
      if (!r.ok) {
        setErr(await r.text());
      } else {
        setEditingId(null);
        setEditDraft("");
        await loadReplies();
        await loadStats();
      }
    } catch {
      setErr("Network error");
    }
    setBusy(null);
  }

  async function rejectReply(replyId: string) {
    setBusy(replyId);
    setErr(null);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/replies/${replyId}/reject`, {
        method: "POST",
        headers,
        body: JSON.stringify({ note: null }),
      });
      if (!r.ok) {
        setErr(await r.text());
      } else {
        await loadReplies();
        await loadStats();
      }
    } catch {
      setErr("Network error");
    }
    setBusy(null);
  }

  async function sendReply(replyId: string) {
    setBusy(replyId);
    setErr(null);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/replies/${replyId}/send`, {
        method: "POST",
        headers,
      });
      if (!r.ok) {
        setErr(await r.text());
      } else {
        await loadReplies();
        await loadStats();
      }
    } catch {
      setErr("Network error");
    }
    setBusy(null);
  }

  /* ── Access check ─────────────────────────────────────────────────── */

  const role = profile?.role || "";
  const roleType = profile?.role_type || "";
  if (!["ceo", "hos"].includes(role) && roleType !== "va_manager") {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <p className="text-slate-500">Reply queue access restricted to CEO, HoS, and VA Manager.</p>
      </div>
    );
  }

  /* ── Render ────────────────────────────────────────────────────────── */

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">ARIA Reply Queue</h1>
          <p className="text-sm text-slate-600">
            Inbound prospect replies classified by ARIA. Review and approve before sending.
          </p>
        </div>
        <Link
          href="/crm/ai"
          className="text-sm text-blue-600 hover:text-blue-500 hover:underline"
        >
          Back to ARIA
        </Link>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="flex flex-wrap gap-3">
          {STATUS_TABS.map((tab) => {
            const count = stats[tab.key as keyof QueueStats] ?? 0;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  "rounded-full px-3 py-1 text-sm font-medium transition-colors",
                  activeTab === tab.key
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                )}
              >
                {tab.label}
                {count > 0 && (
                  <span className="ml-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/20 text-xs">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Error */}
      {err && <p className="text-sm text-rose-600">{err}</p>}

      {/* Loading */}
      {loading ? (
        <p className="text-slate-500">Loading replies...</p>
      ) : replies.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center">
          <p className="text-slate-500">No replies in this queue.</p>
        </div>
      ) : (
        <ul className="space-y-4">
          {replies.map((reply) => {
            const prospect = reply.prospects;
            const cls = CLASSIFICATION_LABELS[reply.classification] || CLASSIFICATION_LABELS.pending;
            const isExpanded = expandedId === reply.id;
            const isEditing = editingId === reply.id;
            const confidence = reply.classification_confidence
              ? `${Math.round(reply.classification_confidence * 100)}%`
              : null;
            const sentiment = (reply.metadata?.sentiment as string) || null;
            const objectionType = (reply.metadata?.objection_type as string) || null;

            return (
              <li
                key={reply.id}
                className="rounded-lg border border-slate-200 bg-white shadow-sm"
              >
                {/* Header */}
                <div
                  className="flex cursor-pointer items-start justify-between gap-3 p-4"
                  onClick={() => setExpandedId(isExpanded ? null : reply.id)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-900">
                        {prospect?.company_name || prospect?.domain || "Unknown"}
                      </span>
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", cls.color)}>
                        {cls.label}
                      </span>
                      {confidence && (
                        <span className="text-xs text-slate-500">{confidence} confidence</span>
                      )}
                      {objectionType && reply.classification === "objection" && (
                        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">
                          {objectionType.replace(/_/g, " ")}
                        </span>
                      )}
                      {sentiment && (
                        <span className={cn(
                          "text-xs",
                          sentiment === "positive" ? "text-emerald-600" :
                          sentiment === "negative" ? "text-rose-600" : "text-slate-500"
                        )}>
                          {sentiment}
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-sm text-slate-600">
                      {prospect?.contact_name || reply.reply_from_name || "—"} &middot;{" "}
                      {prospect?.contact_email || reply.reply_from_email || "—"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Score {prospect?.hawk_score ?? "—"} &middot; {prospect?.industry || "—"} &middot;{" "}
                      {timeAgo(reply.reply_received_at)}
                    </p>
                  </div>
                  <span className="text-xs text-slate-400">{isExpanded ? "▲" : "▼"}</span>
                </div>

                {/* Expanded content */}
                {isExpanded && (
                  <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-4">
                    {/* Original reply */}
                    <div>
                      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                        Prospect Reply
                      </p>
                      {reply.reply_subject && (
                        <p className="text-sm font-medium text-slate-700">
                          Subject: {reply.reply_subject}
                        </p>
                      )}
                      <div className="mt-1 rounded bg-slate-50 p-3 text-sm text-slate-800 whitespace-pre-wrap">
                        {reply.reply_content || "(empty)"}
                      </div>
                    </div>

                    {/* Classification reasoning */}
                    {reply.classification_reasoning && (
                      <div>
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                          ARIA Classification Reasoning
                        </p>
                        <p className="text-sm text-slate-600">{reply.classification_reasoning}</p>
                      </div>
                    )}

                    {/* Drafted response */}
                    {reply.draft_body && (
                      <div>
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                          ARIA Drafted Response
                        </p>
                        {reply.draft_subject && (
                          <p className="text-sm font-medium text-slate-700">
                            Subject: {reply.draft_subject}
                          </p>
                        )}
                        {isEditing ? (
                          <textarea
                            className="mt-1 w-full rounded border border-slate-300 p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                            rows={6}
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                          />
                        ) : (
                          <div className="mt-1 rounded bg-blue-50 p-3 text-sm text-slate-800 whitespace-pre-wrap">
                            {reply.draft_body}
                          </div>
                        )}
                        {reply.draft_reasoning && (
                          <p className="mt-1 text-xs text-slate-500 italic">
                            Strategy: {reply.draft_reasoning}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Action buttons */}
                    {reply.status === "pending_review" && (
                      <div className="flex flex-wrap gap-2 pt-2">
                        {isEditing ? (
                          <>
                            <Button
                              size="sm"
                              className="bg-emerald-700 hover:bg-emerald-600"
                              disabled={busy === reply.id}
                              onClick={() => void approveReply(reply.id, editDraft)}
                            >
                              Save &amp; Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setEditingId(null);
                                setEditDraft("");
                              }}
                            >
                              Cancel Edit
                            </Button>
                          </>
                        ) : (
                          <>
                            <Button
                              size="sm"
                              className="bg-emerald-700 hover:bg-emerald-600"
                              disabled={busy === reply.id || !reply.draft_body}
                              onClick={() => void approveReply(reply.id)}
                            >
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={busy === reply.id || !reply.draft_body}
                              onClick={() => {
                                setEditingId(reply.id);
                                setEditDraft(reply.draft_body || "");
                              }}
                            >
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="border-rose-300 text-rose-600 hover:bg-rose-50"
                              disabled={busy === reply.id}
                              onClick={() => void rejectReply(reply.id)}
                            >
                              Reject
                            </Button>
                          </>
                        )}
                      </div>
                    )}

                    {/* Approved: show send button */}
                    {reply.status === "approved" && (
                      <div className="flex gap-2 pt-2">
                        <Button
                          size="sm"
                          className="bg-blue-700 hover:bg-blue-600"
                          disabled={busy === reply.id}
                          onClick={() => void sendReply(reply.id)}
                        >
                          Send Reply
                        </Button>
                      </div>
                    )}

                    {/* Sent: show sent info */}
                    {reply.status === "sent" && reply.sent_at && (
                      <p className="text-sm text-emerald-600">
                        Sent {timeAgo(reply.sent_at)}
                      </p>
                    )}

                    {/* Rejected: show note */}
                    {reply.status === "rejected" && (
                      <p className="text-sm text-rose-600">
                        Rejected{reply.review_note ? `: ${reply.review_note}` : ""}
                      </p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
