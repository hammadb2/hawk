import { Suspense } from "react";
import { CrmLoginForm } from "@/app/crm/login/crm-login-form";

export default function CrmLoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-4 text-zinc-100">
      <Suspense
        fallback={
          <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 text-sm text-zinc-500">Loading…</div>
        }
      >
        <CrmLoginForm />
      </Suspense>
    </div>
  );
}
