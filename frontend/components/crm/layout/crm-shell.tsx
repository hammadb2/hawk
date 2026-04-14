"use client";

import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CrmSidebar } from "@/components/crm/layout/sidebar";
import { CrmTopbar } from "@/components/crm/layout/topbar";
import { CrmMobileNav } from "@/components/crm/layout/mobile-nav";
import { Toaster } from "react-hot-toast";
import { SentryClientInit } from "@/components/crm/sentry-client";
import { lightShell } from "@/lib/portal-ui";

export function CrmShell({ children }: { children: React.ReactNode }) {
  const { authReady, session } = useCrmAuth();

  if (!authReady) {
    return (
      <div className={`flex min-h-screen items-center justify-center ${lightShell.pageBg}`}>
        <div className="flex flex-col items-center gap-3">
          <div className={lightShell.spinnerSm} />
          <p className="text-sm text-slate-600">Loading session…</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return <>{children}</>;
  }

  return (
    <div className={lightShell.pageBg}>
      <SentryClientInit />
      <Toaster
        position="top-center"
        toastOptions={{
          className: "bg-white text-slate-900 border border-slate-200 shadow-sm",
        }}
      />
      <div className="hidden md:block">
        <CrmSidebar />
        <div className="md:pl-16 xl:pl-64">
          <CrmTopbar />
          <main className="min-h-[calc(100vh-3.5rem)] p-4 lg:p-6">{children}</main>
        </div>
      </div>
      <div className="md:hidden">
        <CrmTopbar />
        <main className="min-h-[calc(100vh-7rem)] p-3 pb-24">{children}</main>
        <CrmMobileNav />
      </div>
    </div>
  );
}
