"use client";

import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CrmSidebar } from "@/components/crm/layout/sidebar";
import { CrmTopbar } from "@/components/crm/layout/topbar";
import { CrmMobileNav } from "@/components/crm/layout/mobile-nav";
import { Toaster } from "react-hot-toast";
import { SentryClientInit } from "@/components/crm/sentry-client";
import { AiBubble } from "@/components/crm/ai-bubble";
import { lightShell } from "@/lib/portal-ui";

const crmAppShell = "min-h-dvh bg-crmBg text-slate-200";

export function CrmShell({ children }: { children: React.ReactNode }) {
  const { authReady, session } = useCrmAuth();

  if (!authReady) {
    return (
      <div className={`flex min-h-dvh items-center justify-center ${lightShell.pageBg}`}>
        <div className="flex flex-col items-center gap-3">
          <div className={lightShell.spinnerSm} />
          <p className="text-sm text-slate-600">Loading session…</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return <div className={lightShell.pageBg}>{children}</div>;
  }

  return (
    <div className={crmAppShell}>
      <SentryClientInit />
      <Toaster
        position="top-center"
        toastOptions={{
          className: "bg-crmSurface text-white border border-crmBorder shadow-lg",
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
      <AiBubble />
    </div>
  );
}
