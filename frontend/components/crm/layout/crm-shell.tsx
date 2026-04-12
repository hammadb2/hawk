"use client";

import { useCallback, useEffect, useState } from "react";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CrmSidebar } from "@/components/crm/layout/sidebar";
import { CrmTopbar } from "@/components/crm/layout/topbar";
import { CrmMobileNav } from "@/components/crm/layout/mobile-nav";
import { Toaster } from "react-hot-toast";
import { SentryClientInit } from "@/components/crm/sentry-client";

type Theme = "dark" | "light";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = localStorage.getItem("hawk-crm-theme") as Theme | null;
    if (stored === "light" || stored === "dark") setTheme(stored);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      localStorage.setItem("hawk-crm-theme", next);
      return next;
    });
  }, []);

  return [theme, toggle];
}

export { useTheme };

export function CrmShell({ children }: { children: React.ReactNode }) {
  const { authReady, session } = useCrmAuth();
  const [theme, toggleTheme] = useTheme();

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

  const light = theme === "light";

  return (
    <div
      className={`min-h-screen transition-colors duration-200 ${light ? "bg-zinc-100 text-zinc-900" : "bg-zinc-950 text-zinc-100"}`}
      style={light ? { ["--shell-bg" as string]: "#f4f4f5", ["--shell-fg" as string]: "#18181b" } : undefined}
    >
      <SentryClientInit />
      <Toaster
        position="top-center"
        toastOptions={{
          className: light
            ? "bg-white text-zinc-900 border border-zinc-200"
            : "bg-zinc-900 text-zinc-100 border border-zinc-800",
        }}
      />
      <div className="hidden md:block">
        <CrmSidebar />
        <div className="md:pl-16 xl:pl-64">
          <CrmTopbar theme={theme} toggleTheme={toggleTheme} />
          <main className="min-h-[calc(100vh-3.5rem)] p-4 lg:p-6">{children}</main>
        </div>
      </div>
      <div className="md:hidden">
        <CrmTopbar theme={theme} toggleTheme={toggleTheme} />
        <main className="min-h-[calc(100vh-7rem)] p-3 pb-24">{children}</main>
        <CrmMobileNav />
      </div>
    </div>
  );
}
