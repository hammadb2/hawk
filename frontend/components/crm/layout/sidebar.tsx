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
import { Button } from "@/components/ui/button";

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
  }, [router]);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 hidden md:flex md:flex-col",
        "border-r border-slate-200 bg-white/95 backdrop-blur",
        "w-16 xl:w-64 transition-[width] duration-200"
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-3 xl:px-4">
        <div
          className="flex shrink-0 items-center rounded-lg bg-slate-900 px-2 py-1 shadow-sm ring-1 ring-slate-800/80"
          title="HAWK"
        >
          <img src="/hawk-logo.png" alt="HAWK" className="h-7 w-auto xl:h-8" />
        </div>
        <span className="hidden text-sm font-semibold tracking-tight text-slate-800 xl:inline">CRM</span>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-2 py-2 text-sm font-medium transition-colors xl:px-3",
                active
                  ? "bg-emerald-50 text-slate-900 ring-1 ring-emerald-200/70"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
              title={item.label}
            >
              <span
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
                  active ? "bg-emerald-100/90 text-emerald-700" : "bg-slate-50 text-slate-500"
                )}
              >
                {icons[item.label] ?? <LayoutDashboard size={18} />}
              </span>
              <span className="hidden xl:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-slate-200 p-2">
        <Button
          variant="outline"
          className="w-full justify-center border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100 xl:justify-start"
          onClick={() => void signOut()}
        >
          <LogOut size={16} className="xl:mr-2" />
          <span className="hidden xl:inline">Sign out</span>
        </Button>
      </div>
    </aside>
  );
}
