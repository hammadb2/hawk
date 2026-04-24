"use client";

import { useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export default function OnboardingCompletePage() {
  const supabase = useMemo(() => createClient(), []);
  const [status, setStatus] = useState<string>("pending_review");
  const [userName, setUserName] = useState("");

  useEffect(() => {
    void (async () => {
      const { data: authData } = await supabase.auth.getUser();
      if (!authData.user) {
        window.location.href = "/crm/login";
        return;
      }

      const { data: prof } = await supabase
        .from("profiles")
        .select("full_name,onboarding_status")
        .eq("id", authData.user.id)
        .maybeSingle();

      setUserName(prof?.full_name || "");
      setStatus(prof?.onboarding_status || "pending_review");

      if (prof?.onboarding_status === "approved") {
        setTimeout(() => {
          window.location.href = "/crm/dashboard";
        }, 3000);
      }
    })();
  }, [supabase]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-[#0a0a12]">
      <div className="mx-auto max-w-md text-center">
        {status === "approved" ? (
          <>
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-signal/20">
              <svg className="h-8 w-8 text-signal" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white">Welcome aboard, {userName}!</h1>
            <p className="mt-3 text-sm text-ink-200">
              Your onboarding has been approved. Redirecting you to the CRM...
            </p>
            <div className="mt-6">
              <div className="h-1 w-32 mx-auto overflow-hidden rounded-full bg-ink-800">
                <div className="h-full animate-pulse bg-signal rounded-full" style={{ width: "100%" }} />
              </div>
            </div>
          </>
        ) : status === "rejected" ? (
          <>
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red/100/20">
              <svg className="h-8 w-8 text-red" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white">Onboarding Needs Revision</h1>
            <p className="mt-3 text-sm text-ink-200">
              Your submission was sent back for revision. Please check your email for details.
            </p>
            <button
              onClick={() => (window.location.href = "/onboarding")}
              className="mt-6 rounded-lg bg-signal-400 px-6 py-3 text-sm font-semibold text-white hover:bg-signal-600 transition"
            >
              Return to Onboarding
            </button>
          </>
        ) : (
          <>
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-signal/20">
              <svg className="h-8 w-8 text-signal" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white">Onboarding Submitted</h1>
            <p className="mt-3 text-sm text-ink-200">
              Thanks, {userName}! Your onboarding is pending review. You&apos;ll receive an email once it&apos;s been
              approved.
            </p>
            <div className="mt-6 rounded-lg border border-ink-800 bg-[#161625] p-4">
              <p className="text-xs text-ink-0">
                A manager will review your documents, ID, and quiz results. This usually takes less than 24 hours.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
