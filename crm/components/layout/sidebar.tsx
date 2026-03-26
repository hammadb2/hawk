"use client";

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  GitBranch,
  Users,
  Building2,
  BarChart3,
  Bot,
  UserCog,
  FileText,
  Settings,
  DollarSign,
  LifeBuoy,
  Trophy,
  Shield,
  ChevronLeft,
  ChevronRight,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useCRMStore } from "@/store/crm-store";
import {
  canAccessCharlotte,
  canManageTeam,
  canViewReports,
  canAccessSettings,
  canAccessTickets,
} from "@/lib/auth";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { getInitials, roleShortLabel } from "@/lib/utils";
import { createClient } from "@/lib/supabase";

const NAV_ITEMS = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    roles: ["ceo", "hos", "team_lead", "rep", "csm"],
    badge: null,
  },
  {
    href: "/pipeline",
    label: "Pipeline",
    icon: GitBranch,
    roles: ["ceo", "hos", "team_lead", "rep"],
    badge: "overdue",
  },
  {
    href: "/prospects",
    label: "Prospects",
    icon: Building2,
    roles: ["ceo", "hos", "team_lead", "rep"],
    badge: "uncontacted",
  },
  {
    href: "/clients",
    label: "Clients",
    icon: Users,
    roles: ["ceo", "hos", "team_lead", "rep", "csm"],
    badge: "churn",
  },
  {
    href: "/scoreboard",
    label: "Scoreboard",
    icon: Trophy,
    roles: ["ceo", "hos", "team_lead", "rep"],
    badge: null,
  },
  {
    href: "/charlotte",
    label: "Charlotte",
    icon: Bot,
    roles: ["ceo", "hos"],
    badge: "emails_today",
  },
  {
    href: "/team",
    label: "Team",
    icon: UserCog,
    roles: ["ceo", "hos"],
    badge: "flagged_reps",
  },
  {
    href: "/reports",
    label: "Reports",
    icon: BarChart3,
    roles: ["ceo", "hos", "team_lead"],
    badge: null,
  },
  {
    href: "/earnings",
    label: "My Earnings",
    icon: DollarSign,
    roles: ["rep", "team_lead"],
    badge: null,
  },
  {
    href: "/tickets",
    label: "Support Tickets",
    icon: LifeBuoy,
    roles: ["ceo"],
    badge: "open_tickets",
  },
  {
    href: "/settings",
    label: "Settings",
    icon: Settings,
    roles: ["ceo"],
    badge: null,
  },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { user, sidebarCollapsed, toggleSidebar } = useCRMStore();

  const handleSignOut = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    window.location.href = "/login";
  };

  if (!user) return null;

  const visibleItems = NAV_ITEMS.filter((item) =>
    (item.roles as readonly string[]).includes(user.role)
  );

  return (
    <aside
      className={cn(
        "flex flex-col h-screen bg-surface-1 border-r border-border transition-all duration-200 flex-shrink-0",
        sidebarCollapsed ? "w-14" : "w-56"
      )}
    >
      {/* Logo */}
      <div className={cn(
        "flex items-center h-14 border-b border-border px-3 flex-shrink-0",
        sidebarCollapsed ? "justify-center" : "gap-3"
      )}>
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex-shrink-0">
          <Shield className="w-4 h-4 text-accent-light" />
        </div>
        {!sidebarCollapsed && (
          <div>
            <div className="text-sm font-bold text-text-primary leading-none">HAWK</div>
            <div className="text-2xs font-medium text-text-dim uppercase tracking-widest">CRM</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5 scrollbar-hide">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);

          const linkContent = (
            <Link
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-all group relative",
                isActive
                  ? "bg-surface-2 text-text-primary border-l-2 border-accent"
                  : "text-text-secondary hover:bg-surface-2 hover:text-text-primary border-l-2 border-transparent"
              )}
            >
              <Icon className={cn(
                "flex-shrink-0 transition-colors",
                sidebarCollapsed ? "w-5 h-5" : "w-4 h-4",
                isActive ? "text-accent-light" : "text-text-dim group-hover:text-text-secondary"
              )} />
              {!sidebarCollapsed && (
                <span className="flex-1 min-w-0 truncate">{item.label}</span>
              )}
            </Link>
          );

          if (sidebarCollapsed) {
            return (
              <Tooltip key={item.href}>
                <TooltipTrigger asChild>
                  {linkContent}
                </TooltipTrigger>
                <TooltipContent side="right">
                  {item.label}
                </TooltipContent>
              </Tooltip>
            );
          }

          return <div key={item.href}>{linkContent}</div>;
        })}
      </nav>

      {/* Bottom: User + collapse */}
      <div className="border-t border-border p-2 flex-shrink-0">
        <div className={cn(
          "flex items-center gap-2.5 rounded-lg px-2.5 py-2 mb-1",
          sidebarCollapsed ? "justify-center" : ""
        )}>
          <div className="relative flex-shrink-0">
            <Avatar className="w-7 h-7">
              <AvatarFallback className="text-xs">
                {getInitials(user.name)}
              </AvatarFallback>
            </Avatar>
            <div className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-green border border-surface-1" />
          </div>
          {!sidebarCollapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-text-primary truncate">{user.name}</p>
              <p className="text-2xs text-text-dim truncate">{roleShortLabel(user.role)}</p>
            </div>
          )}
          {!sidebarCollapsed && (
            <button
              onClick={handleSignOut}
              className="p-1 rounded text-text-dim hover:text-red transition-colors"
              title="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center rounded-lg px-2.5 py-1.5 text-text-dim hover:text-text-secondary hover:bg-surface-2 transition-all"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <div className="flex items-center gap-2 text-xs">
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Collapse</span>
            </div>
          )}
        </button>
      </div>
    </aside>
  );
}
