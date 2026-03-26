"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  Plus,
  Trophy,
  MoreHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useCRMStore } from "@/store/crm-store";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

const TABS = [
  { href: "/dashboard", label: "Home", icon: LayoutDashboard },
  { href: "/pipeline", label: "Pipeline", icon: GitBranch },
  { href: null, label: "Add", icon: Plus, isAction: true },
  { href: "/scoreboard", label: "Scores", icon: Trophy },
] as const;

export function MobileNav() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-surface-1 md:hidden safe-area-inset-bottom">
      <div className="flex items-center justify-around h-16 px-2">
        {TABS.map((tab) => {
          const Icon = tab.icon;

          if ("isAction" in tab && tab.isAction) {
            return (
              <DropdownMenu key="quick-add">
                <DropdownMenuTrigger asChild>
                  <button className="flex flex-col items-center justify-center w-11 h-11 rounded-full bg-accent hover:bg-accent/90 text-white transition-all min-w-[44px] min-h-[44px]">
                    <Icon className="w-5 h-5" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="center" side="top" className="w-48 mb-2">
                  <DropdownMenuItem onClick={() => router.push("/prospects?add=true")}>
                    Add Prospect
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push("/pipeline?log_call=true")}>
                    Log Call
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push("/pipeline?add_note=true")}>
                    Add Note
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => router.push("/pipeline?run_scan=true")}>
                    Run Scan
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            );
          }

          const isActive = tab.href && (pathname === tab.href || pathname.startsWith(`${tab.href}/`));

          return (
            <Link
              key={tab.href}
              href={tab.href!}
              className="flex flex-col items-center justify-center gap-0.5 w-11 min-w-[44px] min-h-[44px] rounded-lg transition-colors"
            >
              <Icon
                className={cn(
                  "w-5 h-5 transition-colors",
                  isActive ? "text-accent-light" : "text-text-dim"
                )}
              />
              <span
                className={cn(
                  "text-2xs font-medium transition-colors",
                  isActive ? "text-accent-light" : "text-text-dim"
                )}
              >
                {tab.label}
              </span>
            </Link>
          );
        })}

        {/* More */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex flex-col items-center justify-center gap-0.5 w-11 min-w-[44px] min-h-[44px] rounded-lg">
              <MoreHorizontal className="w-5 h-5 text-text-dim" />
              <span className="text-2xs font-medium text-text-dim">More</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top" className="w-44 mb-2">
            <DropdownMenuItem onClick={() => router.push("/prospects")}>
              Prospects
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/clients")}>
              Clients
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/earnings")}>
              My Earnings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => router.push("/settings")}>
              Settings
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  );
}
