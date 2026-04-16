"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Legacy CRM onboarding page — replaced by the AI Onboarding Portal at /onboarding.
 * Redirects all visitors to the new portal.
 */
export default function CrmOnboardingPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/onboarding");
  }, [router]);

  return (
    <div className="flex items-center justify-center p-12">
      <p className="text-sm text-slate-500">Redirecting to onboarding portal...</p>
    </div>
  );
}
