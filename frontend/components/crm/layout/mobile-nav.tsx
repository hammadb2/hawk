"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { cn } from "@/lib/utils";

const tabs = [
  { href: "/crm/dashboard", label: "Home", icon: "⌂" },
  { href: "/crm/pipeline", label: "Pipeline", icon: "≡" },
  { href: "/crm/pipeline?add=1", label: "Add", icon: "+" },
  { href: "/crm/scoreboard", label: "Score", icon: "▲" },
  { href: "/crm/dashboard?more=1", label: "More", icon: "⋯" },
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
    <nav className="fixed bottom-0 left-0 right-0 z-40 flex border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] md:hidden">
      {tabs.map((t) => {
        const active = pathname === t.href.split("?")[0];
        return (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "flex min-h-[44px] min-w-0 flex-1 flex-col items-center justify-center gap-0.5 py-1 text-[10px] text-slate-600",
              active && "text-emerald-600"
            )}
          >
            <span className="text-lg leading-none">{t.icon}</span>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
