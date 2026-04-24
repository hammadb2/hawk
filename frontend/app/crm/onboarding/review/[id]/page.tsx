"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLiveEffect } from "@/lib/hooks/use-refresh-signal";
import { useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import toast from "react-hot-toast";
import { crmFieldSurface, crmSurfaceCard } from "@/lib/crm/crm-surface";

interface ReviewDetail {
  session: {
    id: string;
    profile_id: string;
    status: string;
    agreed_terms: Record<string, unknown> | null;
    current_step: number;
    created_at: string;
  };
  profile: {
    full_name: string;
    email: string;
    role: string;
    role_type: string;
  };
  personal_details: Record<string, string> | null;
  bank_details: Record<string, string> | null;
  documents: { document_type: string; signed_at: string; file_url: string }[];
  quiz_results: { module: string; score: number; passed: boolean }[];
  submission: { government_id_url: string | null } | null;
}

export default function OnboardingReviewDetailPage() {
  const params = useParams();
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const { profile, session } = useCrmAuth();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [rejectionReason, setRejectionReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const sessionId = params.id as string;

  const load = useCallback(async () => {
    if (!session?.access_token || !sessionId) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/review/${sessionId}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        setDetail(await r.json());
      }
    } catch (err) {
      console.error("Failed to load review detail:", err);
    }
    setLoading(false);
  }, [session?.access_token, sessionId]);

  useLiveEffect(() => {
    void load();
  }, [load]);

  async function handleAction(action: "approve" | "reject") {
    if (!session?.access_token) return;
    setSubmitting(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/review`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          action,
          reason: action === "reject" ? rejectionReason : undefined,
        }),
      });
      if (r.ok) {
        toast.success(action === "approve" ? "Onboarding approved" : "Onboarding rejected");
        router.push("/crm/onboarding/review");
      } else {
        const err = await r.json();
        toast.error(err.detail || "Action failed");
      }
    } catch {
      toast.error("Network error");
    }
    setSubmitting(false);
  }

  if (!profile || (profile.role !== "ceo" && profile.role !== "hos" && profile.role_type !== "va_manager")) {
    return (
      <div className="p-8 text-center">
        <p className="text-ink-0">You do not have permission to view this page.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-8 text-center">
        <p className="text-ink-0">Submission not found.</p>
      </div>
    );
  }

  const { profile: hireProfile, personal_details, bank_details, documents, quiz_results, submission } = detail;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => router.push("/crm/onboarding/review")}
            className="mb-2 text-xs text-signal hover:text-signal-400"
          >
            &larr; Back to queue
          </button>
          <h1 className="text-xl font-semibold text-white">
            {hireProfile.full_name}&apos;s Onboarding
          </h1>
          <p className="text-sm text-ink-200">
            {hireProfile.email} &middot; {hireProfile.role_type || hireProfile.role}
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            detail.session.status === "pending_review"
              ? "bg-signal/15 text-signal-200 ring-1 ring-signal/30"
              : detail.session.status === "approved"
                ? "bg-signal/15 text-signal-200 ring-1 ring-signal/30"
                : "bg-red/100/15 text-red ring-1 ring-red/30"
          }`}
        >
          {detail.session.status === "pending_review" ? "Pending Review" : detail.session.status}
        </span>
      </div>

      {/* Personal Details */}
      <Section title="Personal Details">
        {personal_details ? (
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(personal_details).map(([k, v]) => (
              <div key={k}>
                <p className="text-xs text-ink-0">{k.replace(/_/g, " ")}</p>
                <p className="text-sm text-ink-100">{v || "—"}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-200">Not submitted yet.</p>
        )}
      </Section>

      {/* Bank Details */}
      <Section title="Bank Details">
        {bank_details ? (
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(bank_details).map(([k, v]) => (
              <div key={k}>
                <p className="text-xs text-ink-0">{k.replace(/_/g, " ")}</p>
                <p className="text-sm text-ink-100">{v || "—"}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-200">Not submitted yet.</p>
        )}
      </Section>

      {/* Government ID */}
      <Section title="Government ID">
        {submission?.government_id_url ? (
          <a
            href={submission.government_id_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-signal hover:underline"
          >
            View uploaded ID
          </a>
        ) : (
          <p className="text-sm text-ink-200">Not uploaded yet.</p>
        )}
      </Section>

      {/* Signed Documents */}
      <Section title="Signed Documents">
        {documents.length > 0 ? (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div key={doc.document_type} className={`flex items-center justify-between px-3 py-2 ${crmFieldSurface}`}>
                <span className="text-sm font-medium text-ink-100">{doc.document_type.replace("_", " ")}</span>
                <div className="flex items-center gap-3">
                  {doc.file_url && (
                    <a href={doc.file_url} target="_blank" rel="noopener noreferrer" className="text-xs text-signal hover:underline">
                      View PDF
                    </a>
                  )}
                  <span className="text-xs text-ink-0">
                    Signed {new Date(doc.signed_at).toLocaleString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-200">No documents signed yet.</p>
        )}
      </Section>

      {/* Quiz Results */}
      <Section title="Quiz Results">
        {quiz_results.length > 0 ? (
          <div className="space-y-2">
            {quiz_results.map((q) => (
              <div key={q.module} className={`flex items-center justify-between px-3 py-2 ${crmFieldSurface}`}>
                <span className="text-sm text-ink-100">{q.module.replace(/_/g, " ")}</span>
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-medium ${q.passed ? "text-signal" : "text-red"}`}>
                    {q.score}%
                  </span>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${q.passed ? "bg-signal/15 text-signal-200" : "bg-red/100/15 text-red"}`}>
                    {q.passed ? "Passed" : "Failed"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-200">No quizzes completed yet.</p>
        )}
      </Section>

      {/* Agreed Terms */}
      {detail.session.agreed_terms && (
        <Section title="Agreed Terms">
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(detail.session.agreed_terms).map(([k, v]) => (
              <div key={k}>
                <p className="text-xs text-ink-0">{k.replace(/_/g, " ")}</p>
                <p className="text-sm text-ink-100">{String(v) || "—"}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Actions */}
      {detail.session.status === "pending_review" && (
        <div className={`p-4 ${crmSurfaceCard}`}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => void handleAction("approve")}
              disabled={submitting}
              className="rounded-lg bg-signal-400 px-6 py-2.5 text-sm font-semibold text-white hover:bg-signal-600 disabled:opacity-50 transition"
            >
              Approve
            </button>
            <button
              onClick={() => setShowReject(!showReject)}
              disabled={submitting}
              className="rounded-lg bg-red/15 px-6 py-2.5 text-sm font-semibold text-white hover:bg-red/15 disabled:opacity-50 transition"
            >
              Reject
            </button>
          </div>
          {showReject && (
            <div className="mt-3 space-y-2">
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Reason for rejection (required)..."
                className={`w-full px-3 py-2 text-sm placeholder:text-ink-0 focus:border-signal/50 focus:outline-none ${crmFieldSurface}`}
                rows={3}
              />
              <button
                onClick={() => void handleAction("reject")}
                disabled={submitting || !rejectionReason.trim()}
                className="rounded-lg bg-red/15 px-4 py-2 text-sm font-semibold text-white hover:bg-red/15 disabled:opacity-50 transition"
              >
                Confirm Rejection
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={`p-4 ${crmSurfaceCard}`}>
      <h2 className="mb-3 text-sm font-semibold text-white">{title}</h2>
      {children}
    </div>
  );
}
