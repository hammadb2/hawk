"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface PipelineStep {
  key: string;
  label: string;
  description: string;
}

const PIPELINE_STEPS: PipelineStep[] = [
  { key: "apify_discover", label: "Apify Discovery", description: "Discovering leads via Google Maps + LinkedIn + Leads Finder" },
  { key: "zerobounce_verify", label: "ZeroBounce Verify", description: "Verifying emails" },
  { key: "hawk_scan", label: "Hawk Domain Scan", description: "Scanning domains for vulnerabilities" },
  { key: "email_generation", label: "Email Generation", description: "Generating personalized emails" },
  { key: "smartlead_load", label: "Smartlead Load", description: "Loading into Smartlead campaign" },
  { key: "completed", label: "Complete", description: "Pipeline run completed" },
];

interface PipelineStatus {
  run_id: string;
  status: string;
  current_step: string;
  vertical: string;
  location: string;
  leads_pulled: number;
  leads_enriched: number;
  leads_verified: number;
  leads_scanned: number;
  emails_generated: number;
  emails_sent: number;
  vulnerabilities_found: number;
  error_message?: string;
}

interface Props {
  runId: string;
  accessToken: string;
  onComplete?: (status: PipelineStatus) => void;
}

function getStepIndex(step: string): number {
  const idx = PIPELINE_STEPS.findIndex((s) => s.key === step);
  return idx >= 0 ? idx : -1;
}

export function PipelineStatusTracker({ runId, accessToken, onComplete }: Props) {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const doneRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const fetchStatus = useCallback(async () => {
    if (doneRef.current) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/aria/pipeline/${runId}/status`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (r.ok) {
        const data = await r.json();
        setStatus(data);
        if (data.status === "completed" || data.status === "failed") {
          doneRef.current = true;
          onCompleteRef.current?.(data);
        }
      } else {
        const err = await r.json().catch(() => ({ detail: "Failed to fetch status" }));
        setError(err.detail || "Failed to fetch pipeline status");
      }
    } catch {
      setError("Connection error fetching pipeline status");
    }
  }, [runId, accessToken]);

  useEffect(() => {
    void fetchStatus();
    const interval = setInterval(() => {
      if (doneRef.current) {
        clearInterval(interval);
        return;
      }
      void fetchStatus();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
          <p className="text-sm text-slate-500">Loading pipeline status...</p>
        </div>
      </div>
    );
  }

  const currentIdx = getStepIndex(status.current_step);
  const isRunning = status.status === "running";
  const isFailed = status.status === "failed";
  const isPaused = status.status === "paused";
  const isCompleted = status.status === "completed";

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${
            isCompleted ? "bg-emerald-500" :
            isFailed ? "bg-red-500" :
            isPaused ? "bg-amber-500" :
            "bg-emerald-500 animate-pulse"
          }`} />
          <span className="text-sm font-semibold text-slate-700">
            ARIA Pipeline — {status.vertical.charAt(0).toUpperCase() + status.vertical.slice(1)}
          </span>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
          isCompleted ? "bg-emerald-100 text-emerald-700" :
          isFailed ? "bg-red-100 text-red-700" :
          isPaused ? "bg-amber-100 text-amber-700" :
          "bg-blue-100 text-blue-700"
        }`}>
          {status.status.charAt(0).toUpperCase() + status.status.slice(1)}
        </span>
      </div>

      {/* Steps */}
      <div className="p-4">
        <div className="space-y-3">
          {PIPELINE_STEPS.map((step, i) => {
            const isDone = isCompleted ? true : i < currentIdx;
            const isCurrent = i === currentIdx && isRunning;
            const isPending = !isDone && !isCurrent;

            return (
              <div key={step.key} className="flex items-center gap-3">
                {/* Step indicator */}
                <div className="flex-shrink-0">
                  {isDone ? (
                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100">
                      <svg className="h-3.5 w-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  ) : isCurrent ? (
                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100">
                      <div className="h-3 w-3 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600" />
                    </div>
                  ) : isFailed && i === currentIdx ? (
                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-red-100">
                      <svg className="h-3.5 w-3.5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </div>
                  ) : (
                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-100">
                      <div className="h-2 w-2 rounded-full bg-slate-300" />
                    </div>
                  )}
                </div>

                {/* Step label */}
                <div className="flex-1 min-w-0">
                  <p className={`text-sm ${
                    isDone ? "text-emerald-700 font-medium" :
                    isCurrent ? "text-blue-700 font-medium" :
                    "text-slate-400"
                  }`}>
                    {step.label}
                  </p>
                  {isCurrent && (
                    <p className="text-xs text-blue-500 mt-0.5">{step.description}...</p>
                  )}
                </div>

                {/* Metric for completed steps */}
                {isDone && (
                  <span className="text-xs text-slate-500 font-mono">
                    {step.key === "apify_discover" && status.leads_pulled > 0 && `${status.leads_pulled} leads`}
                    {step.key === "zerobounce_verify" && status.leads_verified > 0 && `${status.leads_verified} verified`}
                    {step.key === "hawk_scan" && status.leads_scanned > 0 && `${status.leads_scanned} scanned`}
                    {step.key === "email_generation" && status.emails_generated > 0 && `${status.emails_generated} emails`}
                    {step.key === "smartlead_load" && status.emails_sent > 0 && `${status.emails_sent} sent`}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Summary metrics */}
      {(isCompleted || isFailed) && (
        <div className="border-t border-slate-100 bg-slate-50 px-4 py-3">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <p className="text-lg font-bold text-slate-800">{status.leads_pulled}</p>
              <p className="text-xs text-slate-500">Pulled</p>
            </div>
            <div>
              <p className="text-lg font-bold text-emerald-600">{status.vulnerabilities_found}</p>
              <p className="text-xs text-slate-500">Vulns Found</p>
            </div>
            <div>
              <p className="text-lg font-bold text-blue-600">{status.emails_sent}</p>
              <p className="text-xs text-slate-500">Emails Sent</p>
            </div>
          </div>
        </div>
      )}

      {/* Error message */}
      {isFailed && status.error_message && (
        <div className="border-t border-red-100 bg-red-50 px-4 py-2">
          <p className="text-xs text-red-600">{status.error_message}</p>
        </div>
      )}
    </div>
  );
}
