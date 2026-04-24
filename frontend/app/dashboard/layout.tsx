"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/providers/auth-provider";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/findings", label: "Findings" },
  { href: "/dashboard/history", label: "History" },
  { href: "/dashboard/reports", label: "Reports" },
  { href: "/dashboard/domains", label: "Domains" },
  { href: "/dashboard/hawk", label: "Ask HAWK" },
  { href: "/dashboard/breach", label: "Breach Check" },
  { href: "/dashboard/compliance", label: "Compliance" },
  { href: "/dashboard/agency", label: "Agency" },
  { href: "/dashboard/notifications", label: "Notifications" },
  { href: "/dashboard/settings", label: "Settings" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-text-secondary">Loading…</div>
      </div>
    );
  }

  if (!user) {
    router.replace("/login");
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="flex items-center justify-between border-b border-surface-3 bg-ink-800 px-6 py-4 shadow-[0_1px_0_rgba(15,23,42,0.04)]">
        <Link href="/dashboard" className="inline-flex items-center rounded-lg bg-ink-950 px-2.5 py-1.5 ring-1 ring-white/10">
          <img src="/hawk-logo.png" alt="HAWK" className="h-12 w-auto" />
        </Link>
        <div className="flex items-center gap-4">
          <Link href="/dashboard/notifications" className="text-text-secondary hover:text-text-primary text-sm">
            Notifications
          </Link>
          <span className="text-sm text-text-secondary">{user.email}</span>
          <Button variant="ghost" size="sm" onClick={() => logout()}>
            Log out
          </Button>
        </div>
      </header>
      <div className="flex flex-1">
        <aside className="flex w-56 flex-col gap-1 border-r border-surface-3 bg-ink-800 p-4">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                pathname === href
                  ? "bg-signal/10 font-medium text-ink-0 ring-1 ring-signal/20"
                  : "text-text-secondary hover:bg-ink-900 hover:text-ink-0"
              )}
            >
              {label}
            </Link>
          ))}
        </aside>
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
