"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useState, useEffect } from "react";
import {
  LayoutDashboard,
  GitBranch,
  Users,
  Building2,
  BarChart3,
  Bot,
  UserCog,
  Settings,
  DollarSign,
  LifeBuoy,
  Trophy,
  Shield,
  ChevronLeft,
  ChevronRight,
  LogOut,
} from "lucide-react";
import { cn, getInitials, roleShortLabel } from "@/lib/utils";
import { useCRMStore } from "@/store/crm-store";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { getSupabaseClient } from "@/lib/supabase";
import { useNavBadges, type NavBadgeCounts } from "@/hooks/use-nav-badges";

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
    roles: ["ceo", "hos"],
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

type NavBadgeKey = (typeof NAV_ITEMS)[number]["badge"];

function navBadgeCount(key: NavBadgeKey, c: NavBadgeCounts): number | null {
  if (!key) return null;
  switch (key) {
    case "overdue":
      return c.overduePipeline;
    case "uncontacted":
      return c.uncontactedToday;
    case "churn":
      return c.churnRisk;
    case "emails_today":
      return c.charlotteSentToday ?? null;
    case "flagged_reps":
      return c.flaggedReps;
    case "open_tickets":
      return c.openTickets;
    default:
      return null;
  }
}

function NavCountBadge({
  value,
  variant,
}: {
  value: number;
  variant: "red" | "amber" | "yellow" | "accent";
}) {
  if (value <= 0) return null;
  const cls =
    variant === "red"
      ? "bg-red text-white"
      : variant === "amber"
        ? "bg-orange/90 text-white"
        : variant === "yellow"
          ? "bg-yellow/90 text-surface-1"
          : "bg-accent text-white";
  return (
    <span
      className={cn(
        "ml-auto min-w-[1.125rem] h-5 px-1 rounded-full text-2xs font-bold flex items-center justify-center tabular-nums",
        cls
      )}
    >
      {value > 99 ? "99+" : value}
    </span>
  );
}

function CharlotteNavBadge({ value }: { value: number | null }) {
  if (value === null) return null;
  return (
    <span className="ml-auto min-w-[1.125rem] h-5 px-1 rounded-full text-2xs font-bold flex items-center justify-center tabular-nums bg-accent/25 text-accent-light border border-accent/30">
      {value > 99 ? "99+" : value}
    </span>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { user, sidebarCollapsed, toggleSidebar } = useCRMStore();
  const badgeCounts = useNavBadges(user);

  const [isXl, setIsXl] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1280px)");
    const apply = () => setIsXl(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  /** Master spec §03: full labels from 1280px; icon-only from 1024–1279 when sidebar visible. */
  const showLabels = isXl && !sidebarCollapsed;
  const asideWidth = showLabels ? "w-56" : "w-14";

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    // scope: 'local' clears the session from cookies immediately without
    // waiting for a network round-trip. Using 'global' (the default) can
    // stall if the auth server is slow, leaving cookies intact so the
    // middleware redirects the user straight back to the dashboard.
    await supabase.auth.signOut({ scope: "local" });
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
        asideWidth
      )}
    >
      {/* Logo */}
      <div className={cn(
        "flex items-center h-14 border-b border-border px-3 flex-shrink-0",
        showLabels ? "gap-3" : "justify-center"
      )}>
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex-shrink-0">
          <Shield className="w-4 h-4 text-accent-light" />
        </div>
        {showLabels && (
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
          const rawCount = navBadgeCount(item.badge, badgeCounts);
          const numericBadge =
            item.badge && item.badge !== "emails_today" && typeof rawCount === "number" ? rawCount : 0;

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
              <Icon
                className={cn(
                  "flex-shrink-0 transition-colors",
                  showLabels ? "w-4 h-4" : "w-5 h-5",
                  isActive ? "text-accent-light" : "text-text-dim group-hover:text-text-secondary"
                )}
              />
              {showLabels && (
                <span className="flex-1 min-w-0 truncate">{item.label}</span>
              )}
              {showLabels && item.badge === "emails_today" && (
                <CharlotteNavBadge value={badgeCounts.charlotteSentToday} />
              )}
              {showLabels && item.badge === "overdue" && (
                <NavCountBadge value={numericBadge} variant="red" />
              )}
              {showLabels && item.badge === "uncontacted" && (
                <NavCountBadge value={numericBadge} variant="amber" />
              )}
              {showLabels && item.badge === "churn" && (
                <NavCountBadge value={numericBadge} variant="red" />
              )}
              {showLabels && item.badge === "flagged_reps" && (
                <NavCountBadge value={numericBadge} variant="yellow" />
              )}
              {showLabels && item.badge === "open_tickets" && (
                <NavCountBadge value={numericBadge} variant="red" />
              )}
            </Link>
          );

          if (!showLabels) {
            const charlotteDot =
              item.badge === "emails_today" &&
              badgeCounts.charlotteSentToday !== null &&
              badgeCounts.charlotteSentToday > 0;
            const alertDot = item.badge && item.badge !== "emails_today" && numericBadge > 0;

            return (
              <Tooltip key={item.href}>
                <TooltipTrigger asChild>
                  <div className="relative">
                    {linkContent}
                    {alertDot && (
                      <span className="absolute top-1.5 right-1 w-2 h-2 rounded-full bg-red ring-2 ring-surface-1 pointer-events-none" />
                    )}
                    {charlotteDot && !alertDot && (
                      <span className="absolute top-1.5 right-1 w-2 h-2 rounded-full bg-accent ring-2 ring-surface-1 pointer-events-none" />
                    )}
                  </div>
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
          !showLabels ? "justify-center" : ""
        )}>
          <div className="relative flex-shrink-0">
            <Avatar className="w-7 h-7">
              <AvatarFallback className="text-xs">
                {getInitials(user.name)}
              </AvatarFallback>
            </Avatar>
            <div className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-green border border-surface-1" />
          </div>
          {showLabels && (
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-text-primary truncate">{user.name}</p>
              <p className="text-2xs text-text-dim truncate">{roleShortLabel(user.role)}</p>
            </div>
          )}
          {!showLabels ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="p-1 rounded text-text-dim hover:text-red transition-colors"
                  aria-label="Sign out"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">Sign out</TooltipContent>
            </Tooltip>
          ) : (
            <button
              type="button"
              onClick={handleSignOut}
              className="p-1 rounded text-text-dim hover:text-red transition-colors"
              title="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={toggleSidebar}
          disabled={!isXl}
          title={!isXl ? "Narrow screen — sidebar stays compact" : undefined}
          className={cn(
            "w-full flex items-center justify-center rounded-lg px-2.5 py-1.5 text-text-dim hover:text-text-secondary hover:bg-surface-2 transition-all",
            !isXl && "opacity-40 cursor-not-allowed"
          )}
        >
          {!showLabels ? (
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
