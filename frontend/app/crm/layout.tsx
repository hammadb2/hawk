"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/components/providers/auth-provider";
import { CRMProvider, useCRM } from "@/components/crm/crm-provider";

const NAV = [
  { href: "/crm", label: "Dashboard", icon: "⊞", roles: null },
  { href: "/crm/pipeline", label: "Pipeline", icon: "▤", roles: null },
  { href: "/crm/prospects", label: "Prospects", icon: "＋👤", roles: null },
  { href: "/crm/clients", label: "Clients", icon: "🛡", roles: null },
  { href: "/crm/scoreboard", label: "Scoreboard", icon: "🏆", roles: null },
  { href: "/crm/charlotte", label: "Charlotte", icon: "🤖", roles: ["ceo", "head_of_sales"] },
  { href: "/crm/team", label: "Team", icon: "👥", roles: ["ceo", "head_of_sales", "team_lead"] },
  { href: "/crm/reports", label: "Reports", icon: "📊", roles: ["ceo", "head_of_sales", "team_lead"] },
  { href: "/crm/earnings", label: "My Earnings", icon: "💰", roles: null },
  { href: "/crm/settings", label: "Settings", icon: "⚙", roles: ["ceo"] },
];

function CRMSidebar() {
  const pathname = usePathname();
  const { crmUser } = useCRM();

  const visible = NAV.filter(
    (item) => !item.roles || (crmUser && item.roles.includes(crmUser.crm_role))
  );

  return (
    <aside className="w-56 border-r border-surface-3 flex flex-col py-4 px-2 gap-1 shrink-0">
      {visible.map((item) => {
        const active = pathname === item.href || (item.href !== "/crm" && pathname.startsWith(item.href));
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors",
              active
                ? "bg-purple-50 text-purple-700 font-medium border-l-2 border-purple-600"
                : "text-text-secondary hover:bg-surface-2 hover:text-text-primary"
            )}
          >
            <span className="text-base">{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </aside>
  );
}

function CRMShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading: authLoading, token, logout } = useAuth();
  const { crmUser, loading: crmLoading } = useCRM();

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  if (authLoading || crmLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="text-text-secondary text-sm">Loading CRM…</span>
      </div>
    );
  }

  if (!user) return null;

  if (!crmUser) {
    return (
      <div className="min-h-screen flex items-center justify-center flex-col gap-4">
        <p className="text-text-secondary">You don't have access to the CRM.</p>
        <Link href="/dashboard" className="text-purple-600 underline text-sm">← Back to HAWK Dashboard</Link>
      </div>
    );
  }

  const displayName = [crmUser.first_name, crmUser.last_name].filter(Boolean).join(" ") || crmUser.email;

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b border-surface-3 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <Link href="/crm">
            <img src="/hawk-logo.png" alt="HAWK" className="h-8 w-auto" />
          </Link>
          <span className="text-xs font-semibold uppercase tracking-wider text-purple-600 bg-purple-50 px-2 py-0.5 rounded">CRM</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-text-secondary">{displayName}</span>
          <span className="text-xs text-text-secondary capitalize bg-surface-2 px-2 py-0.5 rounded">{crmUser.crm_role.replace("_", " ")}</span>
          <Link href="/dashboard" className="text-xs text-text-secondary hover:text-purple-600">← HAWK Dashboard</Link>
          <button onClick={logout} className="text-xs text-text-secondary hover:text-red-500">Log out</button>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <CRMSidebar />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}

export default function CRMLayout({ children }: { children: React.ReactNode }) {
  return (
    <CRMProvider>
      <CRMShell>{children}</CRMShell>
    </CRMProvider>
  );
}
