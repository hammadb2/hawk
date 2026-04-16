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
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20">
              <svg className="h-8 w-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white">Welcome aboard, {userName}!</h1>
            <p className="mt-3 text-sm text-slate-400">
              Your onboarding has been approved. Redirecting you to the CRM...
            </p>
            <div className="mt-6">
              <div className="h-1 w-32 mx-auto overflow-hidden rounded-full bg-slate-800">
                <div className="h-full animate-pulse bg-emerald-500 rounded-full" style={{ width: "100%" }} />
              </div>
            </div>
          </>
        ) : status === "rejected" ? (
          <>
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/20">
              <svg className="h-8 w-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white">Onboarding Needs Revision</h1>
            <p className="mt-3 text-sm text-slate-400">
              Your submission was sent back for revision. Please check your email for details.
            </p>
            <button
              onClick={() => (window.location.href = "/onboarding")}
              className="mt-6 rounded-lg bg-emerald-600 px-6 py-3 text-sm font-semibold text-white hover:bg-emerald-700 transition"
            >
              Return to Onboarding
            </button>
          </>
        ) : (
          <>
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/20">
              <svg className="h-8 w-8 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white">Onboarding Submitted</h1>
            <p className="mt-3 text-sm text-slate-400">
              Thanks, {userName}! Your onboarding is pending review. You&apos;ll receive an email once it&apos;s been
              approved.
            </p>
            <div className="mt-6 rounded-lg border border-slate-800 bg-[#161625] p-4">
              <p className="text-xs text-slate-500">
                A manager will review your documents, ID, and quiz results. This usually takes less than 24 hours.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
