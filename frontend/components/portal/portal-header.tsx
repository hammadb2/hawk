"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

const NAV_LINKS = [
  { href: "/portal/ask", label: "Ask HAWK" },
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
      className="text-zinc-400 hover:text-[#00C48C] disabled:opacity-50"
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
      <header className="border-b border-zinc-800/80 bg-[#07060C]/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
          <Link href="https://securedbyhawk.com" className="flex items-center gap-2">
            <img src="/hawk-logo.png" alt="HAWK" className="h-10 w-auto" />
            <span className="rounded-md bg-[#00C48C]/15 px-2 py-0.5 text-xs font-medium text-[#00C48C]">Client</span>
          </Link>
          <p className="text-sm text-zinc-500">Portal sign in</p>
        </div>
      </header>
    );
  }

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  return (
    <header className="border-b border-zinc-800/80 bg-[#07060C]/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
        <Link href="/portal" className="flex items-center gap-2">
          <img src="/hawk-logo.png" alt="HAWK" className="h-10 w-auto" />
          <span className="rounded-md bg-[#00C48C]/15 px-2 py-0.5 text-xs font-medium text-[#00C48C]">Client</span>
        </Link>

        {/* Mobile menu toggle */}
        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 lg:hidden"
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

        {/* Desktop nav */}
        <nav className="hidden flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-400 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={isActive(link.href) ? "font-medium text-[#00C48C]" : "hover:text-[#00C48C]"}
            >
              {link.label}
            </Link>
          ))}
          <PortalSignOut />
        </nav>
      </div>

      {/* Mobile nav */}
      {menuOpen && (
        <nav className="border-t border-zinc-800/60 px-4 pb-4 pt-3 lg:hidden">
          <div className="grid grid-cols-2 gap-2 text-sm">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className={`rounded-lg px-3 py-2 ${
                  isActive(link.href)
                    ? "bg-[#00C48C]/10 font-medium text-[#00C48C]"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </div>
          <div className="mt-3 border-t border-zinc-800/60 pt-3">
            <PortalSignOut />
          </div>
        </nav>
      )}
    </header>
  );
}
