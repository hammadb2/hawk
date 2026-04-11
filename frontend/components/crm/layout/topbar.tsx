"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { AddProspectModal } from "@/components/crm/prospect/add-prospect-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { CrmNotificationRow, Prospect } from "@/lib/crm/types";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";

type TopbarProps = { theme?: "dark" | "light"; toggleTheme?: () => void };

export function CrmTopbar({ theme, toggleTheme }: TopbarProps = {}) {
  const router = useRouter();
  const { profile, session, signOut } = useCrmAuth();
  const supabase = useMemo(() => createClient(), []);
  const [searchOpen, setSearchOpen] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Prospect[]>([]);
  const [notifOpen, setNotifOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [notifs, setNotifs] = useState<CrmNotificationRow[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const notifOpenRef = useRef(false);
  notifOpenRef.current = notifOpen;

  const runSearch = useCallback(
    async (query: string) => {
      if (!query.trim()) {
        setResults([]);
        return;
      }
      const term = `%${query.trim()}%`;
      const [byName, byDomain] = await Promise.all([
        supabase.from("prospects").select("id, company_name, domain, stage").ilike("company_name", term).limit(10),
        supabase.from("prospects").select("id, company_name, domain, stage").ilike("domain", term).limit(10),
      ]);
      if (byName.error) {
        toast.error(byName.error.message);
        return;
      }
      if (byDomain.error) {
        toast.error(byDomain.error.message);
        return;
      }
      const map = new Map<string, Prospect>();
      for (const row of [...(byName.data as Prospect[]), ...(byDomain.data as Prospect[])]) {
        map.set(row.id, row);
      }
      setResults(Array.from(map.values()).slice(0, 10));
    },
    [supabase]
  );

  const refreshUnread = useCallback(async () => {
    if (!profile?.id) return;
    const { count } = await supabase
      .from("notifications")
      .select("*", { count: "exact", head: true })
      .eq("user_id", profile.id)
      .eq("read", false);
    setUnread(count ?? 0);
  }, [profile?.id, supabase]);

  const loadNotifs = useCallback(async () => {
    if (!profile?.id) return;
    const { data, error } = await supabase
      .from("notifications")
      .select("*")
      .eq("user_id", profile.id)
      .order("created_at", { ascending: false })
      .limit(30);
    if (error) {
      toast.error(error.message);
      return;
    }
    setNotifs((data ?? []) as CrmNotificationRow[]);
    await refreshUnread();
  }, [profile?.id, supabase, refreshUnread]);

  useEffect(() => {
    const t = setTimeout(() => void runSearch(q), 200);
    return () => clearTimeout(t);
  }, [q, runSearch]);

  useEffect(() => {
    void refreshUnread();
  }, [refreshUnread]);

  useEffect(() => {
    if (notifOpen) void loadNotifs();
  }, [notifOpen, loadNotifs]);

  useEffect(() => {
    if (!profile?.id) return;
    const ch = supabase
      .channel(`crm-notifs-${profile.id}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "notifications", filter: `user_id=eq.${profile.id}` },
        () => {
          void refreshUnread();
          if (notifOpenRef.current) void loadNotifs();
        }
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(ch);
    };
  }, [profile?.id, supabase, refreshUnread, loadNotifs]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function onNotifClick(n: CrmNotificationRow) {
    await supabase.from("notifications").update({ read: true }).eq("id", n.id);
    setNotifs((prev) => prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
    await refreshUnread();
    if (n.link) {
      setNotifOpen(false);
      router.push(n.link);
    }
  }

  const roleLabel = profile?.role?.replace("_", " ") ?? "";

  return (
    <>
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-2 border-b border-zinc-800 bg-zinc-950/90 px-3 backdrop-blur md:px-4">
        <Button
          variant="outline"
          size="sm"
          className="hidden border-zinc-700 bg-zinc-900 text-zinc-200 md:inline-flex"
          onClick={() => setSearchOpen(true)}
        >
          Search <kbd className="ml-2 rounded border border-zinc-600 px-1 text-[10px] text-zinc-500">⌘K</kbd>
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="border-zinc-700 bg-zinc-900 text-zinc-200 md:hidden"
          onClick={() => setSearchOpen(true)}
        >
          Search
        </Button>

        <div className="flex items-center gap-2">
          {toggleTheme && (
            <Button
              variant="ghost"
              size="sm"
              className="text-zinc-300"
              onClick={toggleTheme}
              aria-label="Toggle theme"
            >
              {theme === "light" ? "🌙" : "☀️"}
            </Button>
          )}

          <div className="relative">
            <Button
              variant="ghost"
              size="sm"
              className="relative text-zinc-300"
              onClick={() => setNotifOpen((v) => !v)}
              aria-label="Notifications"
            >
              🔔
              {unread > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-rose-600 px-1 text-[10px] font-medium text-white">
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </Button>
            {notifOpen && (
              <div className="absolute right-0 mt-2 max-h-[min(70vh,420px)] w-80 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 shadow-xl">
                <div className="border-b border-zinc-800 px-3 py-2 text-xs font-medium text-zinc-500">Notifications</div>
                <ul className="max-h-80 overflow-y-auto p-2">
                  {notifs.length === 0 && <li className="px-2 py-6 text-center text-sm text-zinc-500">No notifications yet.</li>}
                  {notifs.map((n) => (
                    <li key={n.id}>
                      <button
                        type="button"
                        onClick={() => void onNotifClick(n)}
                        className={cn(
                          "w-full rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-zinc-900",
                          !n.read && "bg-zinc-900/80"
                        )}
                      >
                        <div className="font-medium text-zinc-200">{n.title}</div>
                        <div className="text-xs text-zinc-500">{n.message}</div>
                        <div className="mt-1 text-[10px] text-zinc-600">{new Date(n.created_at).toLocaleString()}</div>
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="border-t border-zinc-800 p-2">
                  <Button size="sm" variant="outline" className="w-full border-zinc-700" onClick={() => setNotifOpen(false)}>
                    Close
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="relative">
            <Button size="sm" className="bg-emerald-600 text-white hover:bg-emerald-500" onClick={() => setMenuOpen((v) => !v)}>
              + Quick add
            </Button>
            {menuOpen && (
              <div className="absolute right-0 z-20 mt-2 w-52 rounded-lg border border-zinc-800 bg-zinc-950 py-1 shadow-xl">
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900"
                  onClick={() => {
                    setMenuOpen(false);
                    if (!session?.user?.id) {
                      toast.error("Sign in required");
                      return;
                    }
                    setAddOpen(true);
                  }}
                >
                  Add prospect
                </button>
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900"
                  onClick={() => {
                    setMenuOpen(false);
                    router.push("/crm/pipeline");
                    toast.success("Open a prospect card to log a call or add notes.");
                  }}
                >
                  Log call / note / scan
                </button>
                <Link
                  href="/crm/tickets"
                  className="block px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900"
                  onClick={() => setMenuOpen(false)}
                >
                  Support ticket
                </Link>
              </div>
            )}
          </div>

          <div className="relative">
            <button
              type="button"
              className="flex items-center gap-2 rounded-lg border border-zinc-800 px-2 py-1 text-left text-sm"
              onClick={() => signOut()}
              title="Sign out"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-800 text-xs font-medium">
                {(profile?.full_name ?? profile?.email ?? "?").slice(0, 2).toUpperCase()}
              </span>
              <span className="hidden max-w-[8rem] truncate lg:inline">
                <span className="block truncate font-medium text-zinc-100">{profile?.full_name ?? "User"}</span>
                <span className="block truncate text-[11px] uppercase tracking-wide text-zinc-500">{roleLabel}</span>
              </span>
            </button>
          </div>
        </div>
      </header>

      {session?.user?.id && <AddProspectModal open={addOpen} onOpenChange={setAddOpen} sessionUserId={session.user.id} />}

      <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
        <DialogContent className="max-w-lg border-zinc-800 bg-zinc-950">
          <DialogHeader>
            <DialogTitle className="text-zinc-100">Global search</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="Company or domain…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="border-zinc-700 bg-zinc-900 text-zinc-100"
          />
          <ul className="max-h-64 space-y-1 overflow-y-auto text-sm">
            {results.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/crm/prospects/${r.id}`}
                  className="block rounded-md px-2 py-2 hover:bg-zinc-900"
                  onClick={() => setSearchOpen(false)}
                >
                  <span className="font-medium text-zinc-100">{r.company_name ?? r.domain}</span>
                  <span className="ml-2 text-zinc-500">{r.domain}</span>
                </Link>
              </li>
            ))}
            {q && !results.length && <li className="px-2 py-4 text-zinc-500">No matches</li>}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
