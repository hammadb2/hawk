import { Suspense } from "react";
import { CrmLoginForm } from "@/app/crm/login/crm-login-form";

export default function CrmLoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#050508] px-4 text-ink-100">
      <Suspense
        fallback={
          <div className="w-full max-w-md rounded-2xl border border-[#1e1e2e] bg-[#111118] p-8 text-sm text-ink-200">Loading…</div>
        }
      >
        <CrmLoginForm />
      </Suspense>
    </div>
  );
}
