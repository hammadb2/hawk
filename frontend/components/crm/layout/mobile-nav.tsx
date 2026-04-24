"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { LayoutDashboard, Kanban, Plus, Trophy, MoreHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = { href: string; label: string; icon: ReactNode };

const tabs: Tab[] = [
  { href: "/crm/dashboard", label: "Home", icon: <LayoutDashboard size={20} /> },
  { href: "/crm/pipeline", label: "Pipeline", icon: <Kanban size={20} /> },
  { href: "/crm/pipeline?add=1", label: "Add", icon: <Plus size={20} /> },
  { href: "/crm/scoreboard", label: "Score", icon: <Trophy size={20} /> },
  { href: "/crm/dashboard?more=1", label: "More", icon: <MoreHorizontal size={20} /> },
];

export function CrmMobileNav() {
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    router.prefetch("/crm/pipeline");
    router.prefetch("/crm/prospects");
    router.prefetch("/crm/clients");
    router.prefetch("/crm/dashboard");
  }, [router]);
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 flex border-t border-[#1e1e2e] bg-[#0d0d14]/95 backdrop-blur pb-[env(safe-area-inset-bottom)] md:hidden">
      {tabs.map((t) => {
        const active = pathname === t.href.split("?")[0];
        return (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "flex min-h-[44px] min-w-0 flex-1 flex-col items-center justify-center gap-0.5 py-1 text-[10px] text-ink-0",
              active && "text-signal"
            )}
          >
            <span className="leading-none">{t.icon}</span>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
