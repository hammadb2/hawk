import { Suspense } from "react";
import { CrmLoginForm } from "@/app/crm/login/crm-login-form";

export default function CrmLoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-white px-4 text-slate-900">
      <Suspense
        fallback={
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-slate-50 p-8 text-sm text-slate-600">Loading…</div>
        }
      >
        <CrmLoginForm />
      </Suspense>
    </div>
  );
}
