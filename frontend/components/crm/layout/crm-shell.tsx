"use client";

import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CrmSidebar } from "@/components/crm/layout/sidebar";
import { CrmTopbar } from "@/components/crm/layout/topbar";
import { CrmMobileNav } from "@/components/crm/layout/mobile-nav";
import { Toaster } from "react-hot-toast";
import { SentryClientInit } from "@/components/crm/sentry-client";

export function CrmShell({ children }: { children: React.ReactNode }) {
  const { authReady, session } = useCrmAuth();

  if (!authReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-600 border-t-emerald-500" />
          <p className="text-sm text-zinc-400">Loading session…</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <SentryClientInit />
      <Toaster position="top-center" toastOptions={{ className: "bg-zinc-900 text-zinc-100 border border-zinc-800" }} />
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
