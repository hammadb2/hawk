"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, Bell, Plus, Phone, FileText, Scan, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCRMStore } from "@/store/crm-store";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { getInitials, roleShortLabel, formatRelativeTime } from "@/lib/utils";
import { getSupabaseClient } from "@/lib/supabase";

export function TopBar() {
  const router = useRouter();
  const { user, notifications, markRead, markAllRead, globalSearch, setGlobalSearch } = useCRMStore();
  const [searchFocused, setSearchFocused] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut({ scope: "local" });
    window.location.href = "/login";
  };

  // Cmd+K shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === "Escape" && searchFocused) {
        searchRef.current?.blur();
        setGlobalSearch("");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [searchFocused, setGlobalSearch]);

  if (!user) return null;

  return (
    <header className="h-14 flex items-center gap-3 px-4 border-b border-border bg-surface-1 flex-shrink-0">
      {/* Search */}
      <div className={cn(
        "flex items-center gap-2 rounded-lg border transition-all flex-1 max-w-md px-3 h-8",
        searchFocused
          ? "border-accent/60 bg-surface-2 ring-1 ring-accent/20"
          : "border-border bg-surface-2"
      )}>
        <Search className="w-3.5 h-3.5 text-text-dim flex-shrink-0" />
        <input
          ref={searchRef}
          type="text"
          placeholder="Search prospects, clients, domains..."
          value={globalSearch}
          onChange={(e) => setGlobalSearch(e.target.value)}
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-dim focus:outline-none min-w-0"
        />
        {!searchFocused && !globalSearch && (
          <kbd className="hidden sm:flex items-center gap-0.5 text-2xs text-text-dim bg-surface-3 rounded px-1.5 py-0.5 font-mono flex-shrink-0">
            <span>⌘</span><span>K</span>
          </kbd>
        )}
      </div>

      <div className="flex items-center gap-1 ml-auto">
        {/* Quick add */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center justify-center w-8 h-8 rounded-lg text-text-dim hover:text-text-primary hover:bg-surface-2 transition-all border border-transparent hover:border-border">
              <Plus className="w-4 h-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel>Quick Add</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => router.push("/prospects?add=true")}>
              <Plus className="w-3.5 h-3.5" />
              Add Prospect
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/pipeline?log_call=true")}>
              <Phone className="w-3.5 h-3.5" />
              Log Call
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/pipeline?add_note=true")}>
              <FileText className="w-3.5 h-3.5" />
              Add Note
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/pipeline?run_scan=true")}>
              <Scan className="w-3.5 h-3.5" />
              Run Scan
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Notifications */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="relative flex items-center justify-center w-8 h-8 rounded-lg text-text-dim hover:text-text-primary hover:bg-surface-2 transition-all">
              <Bell className="w-4 h-4" />
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center w-4 h-4 text-2xs font-bold text-white bg-red rounded-full">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80 max-h-96 overflow-y-auto">
            <div className="flex items-center justify-between px-2 py-1.5">
              <span className="text-xs font-semibold text-text-primary">Notifications</span>
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="text-2xs text-accent-light hover:text-accent transition-colors"
                >
                  Mark all read
                </button>
              )}
            </div>
            <DropdownMenuSeparator />
            {notifications.length === 0 ? (
              <div className="py-6 text-center text-xs text-text-dim">
                No notifications
              </div>
            ) : (
              notifications.slice(0, 15).map((n) => (
                <DropdownMenuItem
                  key={n.id}
                  onClick={() => {
                    markRead(n.id);
                    if (n.link) router.push(n.link);
                  }}
                  className={cn(
                    "flex flex-col items-start gap-0.5 py-2.5 cursor-pointer",
                    !n.read && "bg-accent/5"
                  )}
                >
                  <div className="flex items-center gap-2 w-full">
                    <span className="flex-1 text-xs font-medium text-text-primary truncate">
                      {n.title}
                    </span>
                    {!n.read && (
                      <span className="w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0" />
                    )}
                  </div>
                  <span className="text-2xs text-text-dim">{n.message}</span>
                  <span className="text-2xs text-text-dim/60">
                    {formatRelativeTime(n.created_at)}
                  </span>
                </DropdownMenuItem>
              ))
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-2 ml-1 pl-2 border-l border-border rounded-lg pr-1 py-0.5 hover:bg-surface-2/80 transition-colors"
            >
              <div className="hidden sm:flex flex-col items-end">
                <span className="text-xs font-medium text-text-primary leading-none">{user.name}</span>
                <span className="text-2xs text-text-dim">{roleShortLabel(user.role)}</span>
              </div>
              <div className="relative">
                <Avatar className="w-7 h-7">
                  <AvatarFallback className="text-xs">{getInitials(user.name)}</AvatarFallback>
                </Avatar>
                <div className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-green border border-surface-1" />
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col space-y-0.5">
                <span className="text-sm font-medium">{user.name}</span>
                <span className="text-2xs text-text-dim">{roleShortLabel(user.role)}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                void handleSignOut();
              }}
              className="text-red focus:text-red gap-2"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
