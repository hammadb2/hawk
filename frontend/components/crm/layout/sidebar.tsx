"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  LayoutDashboard,
  Kanban,
  Users,
  UserCheck,
  Trophy,
  MessageSquareReply,
  ShieldCheck,
  HeartPulse,
  ShieldAlert,
  UsersRound,
  FileBarChart2,
  DollarSign,
  ScrollText,
  Settings,
  Ticket,
  LogOut,
  Bot,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { navVisibleForRole } from "@/lib/crm/nav-config";

const icons: Record<string, ReactNode> = {
  Dashboard: <LayoutDashboard size={18} />,
  Pipeline: <Kanban size={18} />,
  Prospects: <Users size={18} />,
  Clients: <UserCheck size={18} />,
  Scoreboard: <Trophy size={18} />,
  ARIA: <Bot size={18} />,
  Replies: <MessageSquareReply size={18} />,
  Guarantees: <ShieldCheck size={18} />,
  Health: <HeartPulse size={18} />,
  Guardian: <ShieldAlert size={18} />,
  Team: <UsersRound size={18} />,
  Reports: <FileBarChart2 size={18} />,
  Earnings: <DollarSign size={18} />,
  "Audit log": <ScrollText size={18} />,
  Settings: <Settings size={18} />,
  "Support Tickets": <Ticket size={18} />,
};

export function CrmSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { profile, signOut } = useCrmAuth();
  const items = navVisibleForRole(profile?.role);

  useEffect(() => {
    router.prefetch("/crm/pipeline");
    router.prefetch("/crm/prospects");
    router.prefetch("/crm/clients");
    router.prefetch("/crm/dashboard");
    router.prefetch("/crm/guardian");
  }, [router]);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 hidden md:flex md:flex-col",
        "border-r border-[#1e1e2e] bg-[#0d0d14]",
        "w-16 xl:w-64 transition-[width] duration-200"
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-[#1e1e2e] px-3 xl:px-4">
        <div
          className="flex shrink-0 items-center rounded-lg bg-crmSurface px-2 py-1 shadow-sm ring-1 ring-crmBorder"
          title="HAWK"
        >
          <img src="/hawk-logo.png" alt="HAWK" className="h-7 w-auto xl:h-8" />
        </div>
        <span className="hidden text-sm font-semibold tracking-tight text-slate-200 xl:inline">CRM</span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          const isAria = item.label === "ARIA";
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 py-2.5 text-sm font-medium transition-colors xl:px-3",
                active
                  ? "border-l-2 border-emerald-500 bg-emerald-500/10 pl-[calc(0.5rem-2px)] text-emerald-400 xl:rounded-r-lg"
                  : "border-l-2 border-transparent pl-2 text-slate-500 hover:bg-white/5 hover:text-slate-300 xl:rounded-lg xl:px-3"
              )}
              title={item.label}
            >
              <span className={cn("relative flex shrink-0 items-center justify-center text-current", active && "text-emerald-400")}>
                {icons[item.label] ?? <LayoutDashboard size={18} />}
                {isAria && (
                  <span
                    className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse xl:hidden"
                    aria-hidden
                  />
                )}
              </span>
              <span className="hidden items-center gap-2 xl:inline">
                {item.label}
                {isAria && (
                  <span className="inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500 animate-pulse" aria-hidden />
                )}
              </span>
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-[#1e1e2e] p-2">
        <button
          type="button"
          className="flex w-full items-center justify-center gap-0 rounded-lg py-2.5 text-sm text-slate-600 transition-colors hover:bg-white/5 hover:text-slate-400 xl:justify-start xl:px-3 xl:gap-2"
          onClick={() => void signOut()}
        >
          <LogOut size={16} />
          <span className="hidden xl:inline">Sign out</span>
        </button>
      </div>
    </aside>
  );
}
