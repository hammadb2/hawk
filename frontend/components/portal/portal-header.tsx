"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { portal } from "@/lib/portal-ui";

const NAV_LINKS = [
  { href: "/portal/ask", label: "Ask ARIA" },
  { href: "/portal/briefing", label: "Weekly briefing" },
  { href: "/portal/findings", label: "Findings" },
  { href: "/portal/journey", label: "Journey" },
  { href: "/portal/benchmark", label: "Benchmark" },
  { href: "/portal/attack-paths", label: "Attack paths" },
  { href: "/portal/enterprise", label: "Enterprise" },
  { href: "/portal/attacker-simulation", label: "Attacker sim" },
  { href: "/portal/compliance", label: "C-27 primer" },
  { href: "/portal/billing", label: "Billing" },
  { href: "/portal/settings", label: "Settings" },
] as const;

function PortalSignOut() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function handleSignOut() {
    setBusy(true);
    try {
      const supabase = createClient();
      await supabase.auth.signOut({ scope: "local" });
      router.push("/portal/login");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void handleSignOut()}
      disabled={busy}
      className="rounded-full px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50"
    >
      {busy ? "Signing out…" : "Sign out"}
    </button>
  );
}

/** Full app nav only when authenticated area; login stays minimal (no feature links). */
export function PortalHeader() {
  const pathname = usePathname() || "";
  const [menuOpen, setMenuOpen] = useState(false);
  const isLoginOrPublic =
    pathname === "/portal/login" ||
    pathname === "/portal/return" ||
    pathname.startsWith("/portal/auth/");

  if (isLoginOrPublic) {
    return (
      <header className={portal.header}>
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Link href="https://securedbyhawk.com" className="flex items-center gap-2.5" title="HAWK">
            <span className="inline-flex items-center rounded-lg bg-slate-900 px-2 py-1.5 ring-1 ring-slate-800/80">
              <img src="/hawk-logo.png" alt="HAWK" className="h-10 w-auto" />
            </span>
            <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-100">
              Client
            </span>
          </Link>
          <p className="text-sm text-slate-500">Portal sign in</p>
        </div>
      </header>
    );
  }

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");

  return (
    <header className={portal.header}>
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
        <Link href="/portal" className="flex shrink-0 items-center gap-2.5" title="HAWK Client">
          <span className="inline-flex items-center rounded-lg bg-slate-900 px-2 py-1.5 ring-1 ring-slate-800/80">
            <img src="/hawk-logo.png" alt="HAWK" className="h-10 w-auto" />
          </span>
          <span className="hidden rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-100 sm:inline">
            Client
          </span>
        </Link>

        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 lg:hidden"
          onClick={() => setMenuOpen((o) => !o)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
        >
          {menuOpen ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          )}
        </button>

        <nav className="hidden max-w-[calc(100%-11rem)] flex-1 flex-wrap items-center justify-end gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={
                isActive(link.href)
                  ? "rounded-full bg-slate-900 px-3 py-1.5 text-sm font-medium text-white shadow-sm"
                  : "rounded-full px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              }
            >
              {link.label}
            </Link>
          ))}
          <PortalSignOut />
        </nav>
      </div>

      {menuOpen && (
        <nav className="border-t border-slate-200/80 px-4 pb-4 pt-3 lg:hidden">
          <div className="grid grid-cols-2 gap-2 text-sm">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className={
                  isActive(link.href)
                    ? "rounded-xl bg-slate-900 px-3 py-2.5 font-medium text-white shadow-sm"
                    : "rounded-xl px-3 py-2.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }
              >
                {link.label}
              </Link>
            ))}
          </div>
          <div className="mt-3 border-t border-slate-200/80 pt-3">
            <PortalSignOut />
          </div>
        </nav>
      )}
    </header>
  );
}
