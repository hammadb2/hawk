"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { cn } from "@/lib/utils";

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
      <div className="rounded-xl border border-red/40 bg-red/15 p-4">
        <p className="text-sm text-red">{error}</p>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="rounded-xl border border-crmBorder bg-crmSurface2 p-4">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-crmBorder border-t-signal" />
          <p className="text-sm text-ink-0">Loading pipeline status...</p>
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
    <div className="overflow-hidden rounded-xl border border-crmBorder bg-crmSurface shadow-lg">
      <div className="flex items-center justify-between border-b border-crmBorder bg-crmSurface2 px-4 py-3">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              "h-2 w-2 rounded-full",
              isCompleted ? "bg-signal" : isFailed ? "bg-red/100" : isPaused ? "bg-signal" : "animate-pulse bg-signal",
            )}
          />
          <span className="text-sm font-semibold text-white">
            ARIA Pipeline — {status.vertical.charAt(0).toUpperCase() + status.vertical.slice(1)}
          </span>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium",
            isCompleted && "bg-signal/15 text-signal",
            isFailed && "bg-red/100/15 text-red",
            isPaused && "bg-signal/15 text-signal-200",
            !isCompleted && !isFailed && !isPaused && "bg-blue-500/15 text-blue-300",
          )}
        >
          {status.status.charAt(0).toUpperCase() + status.status.slice(1)}
        </span>
      </div>

      <div className="p-4">
        <div className="space-y-3">
          {PIPELINE_STEPS.map((step, i) => {
            const isDone = isCompleted ? true : i < currentIdx;
            const isCurrent = i === currentIdx && isRunning;

            return (
              <div key={step.key} className="flex items-center gap-3">
                <div className="flex-shrink-0">
                  {isDone ? (
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-signal/15 text-signal">
                      <Check className="h-4 w-4" strokeWidth={2.5} />
                    </div>
                  ) : isCurrent ? (
                    <div className="relative flex h-7 w-7 items-center justify-center">
                      <span className="absolute inset-0 rounded-full bg-signal/25 animate-ping" />
                      <span className="relative flex h-7 w-7 items-center justify-center rounded-full border-2 border-signal/60 bg-signal/10 ring-2 ring-signal/30">
                        <span className="h-2.5 w-2.5 rounded-full bg-signal-400 animate-pulse" />
                      </span>
                    </div>
                  ) : isFailed && i === currentIdx ? (
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-red/100/15 text-red">
                      <span className="text-xs font-bold">!</span>
                    </div>
                  ) : (
                    <div className="flex h-7 w-7 items-center justify-center rounded-full border border-crmBorder bg-crmSurface2">
                      <div className="h-2 w-2 rounded-full bg-ink-600" />
                    </div>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-sm",
                      isDone && "font-medium text-signal",
                      isCurrent && "font-medium text-signal-200",
                      !isDone && !isCurrent && "text-ink-0",
                    )}
                  >
                    {step.label}
                  </p>
                  {isCurrent && <p className="mt-0.5 text-xs text-ink-0">{step.description}…</p>}
                </div>

                {isDone && (
                  <span className="font-mono text-xs text-ink-0">
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

      {(isCompleted || isFailed) && (
        <div className="border-t border-crmBorder bg-crmSurface2 px-4 py-3">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <p className="text-lg font-bold text-white">{status.leads_pulled}</p>
              <p className="text-xs text-ink-0">Pulled</p>
            </div>
            <div>
              <p className="text-lg font-bold text-signal">{status.vulnerabilities_found}</p>
              <p className="text-xs text-ink-0">Vulns Found</p>
            </div>
            <div>
              <p className="text-lg font-bold text-blue-400">{status.emails_sent}</p>
              <p className="text-xs text-ink-0">Emails Sent</p>
            </div>
          </div>
        </div>
      )}

      {isFailed && status.error_message && (
        <div className="border-t border-red/30 bg-red/15 px-4 py-2">
          <p className="text-xs text-red">{status.error_message}</p>
        </div>
      )}
    </div>
  );
}

