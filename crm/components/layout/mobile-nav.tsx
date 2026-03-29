"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import {
  LayoutDashboard,
  GitBranch,
  Plus,
  Trophy,
  MoreHorizontal,
  LogOut,
  Users,
  Building2,
  Bot,
  UserCog,
  BarChart3,
  Settings,
  DollarSign,
  LifeBuoy,
} from "lucide-react";
import { getSupabaseClient } from "@/lib/supabase";
import { cn } from "@/lib/utils";
import { useCRMStore } from "@/store/crm-store";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { SubmitTicketModal } from "@/components/tickets/submit-ticket-modal";
import { hasRole } from "@/lib/auth";

export function MobileNav() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useCRMStore((s) => s.user);
  const [reportOpen, setReportOpen] = useState(false);

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut({ scope: "local" });
    window.location.href = "/login";
  };

  if (!user) return null;

  /** Master spec §17 — five primary tabs + More. */
  const pipelineTab =
    user.role === "csm"
      ? { href: "/clients" as const, label: "Clients", icon: Users }
      : { href: "/pipeline" as const, label: "Pipeline", icon: GitBranch };
  const PipelineSecondIcon = pipelineTab.icon;

  return (
    <>
      <SubmitTicketModal open={reportOpen} onClose={() => setReportOpen(false)} />
      <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-surface-1 md:hidden safe-area-inset-bottom">
        <div className="flex items-center justify-around h-16 px-2">
          <Link
            href="/dashboard"
            className="flex flex-col items-center justify-center gap-0.5 w-11 min-w-[44px] min-h-[44px] rounded-lg transition-colors"
          >
            <LayoutDashboard
              className={cn(
                "w-5 h-5 transition-colors",
                pathname === "/dashboard" || pathname.startsWith("/dashboard/")
                  ? "text-accent-light"
                  : "text-text-dim"
              )}
            />
            <span
              className={cn(
                "text-2xs font-medium transition-colors",
                pathname === "/dashboard" || pathname.startsWith("/dashboard/")
                  ? "text-accent-light"
                  : "text-text-dim"
              )}
            >
              Home
            </span>
          </Link>

          <Link
            href={pipelineTab.href}
            className="flex flex-col items-center justify-center gap-0.5 w-11 min-w-[44px] min-h-[44px] rounded-lg transition-colors"
          >
            <PipelineSecondIcon
              className={cn(
                "w-5 h-5 transition-colors",
                pathname === pipelineTab.href || pathname.startsWith(`${pipelineTab.href}/`)
                  ? "text-accent-light"
                  : "text-text-dim"
              )}
            />
            <span
              className={cn(
                "text-2xs font-medium transition-colors",
                pathname === pipelineTab.href || pathname.startsWith(`${pipelineTab.href}/`)
                  ? "text-accent-light"
                  : "text-text-dim"
              )}
            >
              {pipelineTab.label}
            </span>
          </Link>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex flex-col items-center justify-center w-11 h-11 rounded-full bg-accent hover:bg-accent/90 text-white transition-all min-w-[44px] min-h-[44px]"
              >
                <Plus className="w-5 h-5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center" side="top" className="w-52 mb-2">
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
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setReportOpen(true)}>Report Issue</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <Link
            href="/scoreboard"
            className="flex flex-col items-center justify-center gap-0.5 w-11 min-w-[44px] min-h-[44px] rounded-lg transition-colors"
          >
            <Trophy
              className={cn(
                "w-5 h-5 transition-colors",
                pathname === "/scoreboard" || pathname.startsWith("/scoreboard/")
                  ? "text-accent-light"
                  : "text-text-dim"
              )}
            />
            <span
              className={cn(
                "text-2xs font-medium transition-colors",
                pathname === "/scoreboard" || pathname.startsWith("/scoreboard/")
                  ? "text-accent-light"
                  : "text-text-dim"
              )}
            >
              Scores
            </span>
          </Link>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex flex-col items-center justify-center gap-0.5 w-11 min-w-[44px] min-h-[44px] rounded-lg"
              >
                <MoreHorizontal className="w-5 h-5 text-text-dim" />
                <span className="text-2xs font-medium text-text-dim">More</span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" side="top" className="w-52 mb-2">
              {hasRole(user, "ceo", "hos", "team_lead", "rep") && (
                <DropdownMenuItem onClick={() => router.push("/prospects")}>
                  <Building2 className="w-4 h-4 mr-2 opacity-70" />
                  Prospects
                </DropdownMenuItem>
              )}
              {hasRole(user, "ceo", "hos", "team_lead", "rep", "csm") && (
                <DropdownMenuItem onClick={() => router.push("/clients")}>
                  <Users className="w-4 h-4 mr-2 opacity-70" />
                  Clients
                </DropdownMenuItem>
              )}
              {hasRole(user, "ceo", "hos") && (
                <DropdownMenuItem onClick={() => router.push("/charlotte")}>
                  <Bot className="w-4 h-4 mr-2 opacity-70" />
                  Charlotte
                </DropdownMenuItem>
              )}
              {hasRole(user, "ceo", "hos") && (
                <DropdownMenuItem onClick={() => router.push("/team")}>
                  <UserCog className="w-4 h-4 mr-2 opacity-70" />
                  Team
                </DropdownMenuItem>
              )}
              {hasRole(user, "ceo", "hos", "team_lead") && (
                <DropdownMenuItem onClick={() => router.push("/reports")}>
                  <BarChart3 className="w-4 h-4 mr-2 opacity-70" />
                  Reports
                </DropdownMenuItem>
              )}
              {hasRole(user, "rep", "team_lead") && (
                <DropdownMenuItem onClick={() => router.push("/earnings")}>
                  <DollarSign className="w-4 h-4 mr-2 opacity-70" />
                  My Earnings
                </DropdownMenuItem>
              )}
              {hasRole(user, "ceo", "hos") && (
                <DropdownMenuItem onClick={() => router.push("/tickets")}>
                  <LifeBuoy className="w-4 h-4 mr-2 opacity-70" />
                  Support Tickets
                </DropdownMenuItem>
              )}
              {user.role === "ceo" && (
                <DropdownMenuItem onClick={() => router.push("/settings")}>
                  <Settings className="w-4 h-4 mr-2 opacity-70" />
                  Settings
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setReportOpen(true)}>
                <LifeBuoy className="w-4 h-4 mr-2 opacity-70" />
                Report Issue
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => {
                  void handleSignOut();
                }}
                className="text-red focus:text-red gap-2"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </nav>
    </>
  );
}
