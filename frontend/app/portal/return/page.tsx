"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { billingApi } from "@/lib/api";

function PortalReturnInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sessionId = searchParams.get("session_id");
    if (!sessionId) {
      setError("Missing payment session. Return to pricing and try checkout again.");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const { redirect_url } = await billingApi.completeCheckoutSession(sessionId);
        if (!cancelled && redirect_url) {
          window.location.href = redirect_url;
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not complete sign-in.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  if (error) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-signal/30 bg-signal/10 px-6 py-8 text-center text-sm text-signal-800">
        <p>{error}</p>
        <button
          type="button"
          className="mt-4 text-signal underline"
          onClick={() => router.push("/portal/login")}
        >
          Go to portal login
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 text-ink-200">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
      <p className="text-sm">Signing you in…</p>
      <p className="max-w-sm text-center text-xs text-ink-0">
        Finishing your account and redirecting to the secure portal.
      </p>
    </div>
  );
}

export default function PortalReturnPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[50vh] items-center justify-center text-ink-200">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
        </div>
      }
    >
      <PortalReturnInner />
    </Suspense>
  );
}
