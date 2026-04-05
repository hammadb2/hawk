"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { navVisibleForRole } from "@/lib/crm/nav-config";
import { Button } from "@/components/ui/button";

const icons: Record<string, string> = {
  Dashboard: "◉",
  Pipeline: "≡",
  Prospects: "◎",
  Clients: "◈",
  Scoreboard: "▲",
  Charlotte: "✉",
  Team: "👥",
  Reports: "📊",
  Earnings: "$",
  "My Earnings": "$",
  Settings: "⚙",
  "Support Tickets": "🎫",
  Replies: "↩",
  Health: "◆",
};

export function CrmSidebar() {
  const pathname = usePathname();
  const { profile, signOut } = useCrmAuth();
  const items = navVisibleForRole(profile?.role);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 hidden md:flex md:flex-col",
        "border-r border-zinc-800 bg-zinc-950/95 backdrop-blur",
        "w-16 xl:w-64 transition-[width] duration-200"
      )}
    >
      <div className="flex h-14 items-center border-b border-zinc-800 px-3 xl:px-4">
        <span className="font-semibold tracking-tight text-emerald-400 xl:text-lg">HAWK</span>
        <span className="ml-1 hidden text-sm text-zinc-500 xl:inline">CRM</span>
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
                active ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
              )}
              title={item.label}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-zinc-900 text-xl leading-none">
                {icons[item.label] ?? "•"}
              </span>
              <span className="hidden xl:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-zinc-800 p-2">
        <Button
          variant="outline"
          className="w-full justify-center border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800 xl:justify-start"
          onClick={() => void signOut()}
        >
          <span className="xl:mr-2">⎋</span>
          <span className="hidden xl:inline">Sign out</span>
        </Button>
      </div>
    </aside>
  );
}
