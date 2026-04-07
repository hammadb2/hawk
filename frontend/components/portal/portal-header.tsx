"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

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
  const isLoginOrPublic =
    pathname === "/portal/login" ||
    pathname === "/portal/return" ||
    pathname.startsWith("/portal/auth/");

  if (isLoginOrPublic) {
    return (
      <header className="border-b border-zinc-800/80 bg-[#07060C]/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
          <Link href="https://securedbyhawk.com" className="flex items-center gap-2">
            <span className="text-lg font-bold tracking-tight text-zinc-50">HAWK</span>
            <span className="rounded-md bg-[#00C48C]/15 px-2 py-0.5 text-xs font-medium text-[#00C48C]">Client</span>
          </Link>
          <p className="text-sm text-zinc-500">Portal sign in</p>
        </div>
      </header>
    );
  }

  return (
    <header className="border-b border-zinc-800/80 bg-[#07060C]/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
        <Link href="/portal" className="flex items-center gap-2">
          <span className="text-lg font-bold tracking-tight text-zinc-50">HAWK</span>
          <span className="rounded-md bg-[#00C48C]/15 px-2 py-0.5 text-xs font-medium text-[#00C48C]">Client</span>
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-400">
          <Link href="/portal/ask" className="hover:text-[#00C48C]">
            Ask HAWK
          </Link>
          <Link href="/portal/briefing" className="hover:text-[#00C48C]">
            Weekly briefing
          </Link>
          <Link href="/portal/findings" className="hover:text-[#00C48C]">
            Findings
          </Link>
          <Link href="/portal/journey" className="hover:text-[#00C48C]">
            Journey
          </Link>
          <Link href="/portal/benchmark" className="hover:text-[#00C48C]">
            Benchmark
          </Link>
          <Link href="/portal/attack-paths" className="hover:text-[#00C48C]">
            Attack paths
          </Link>
          <Link href="/portal/enterprise" className="hover:text-[#00C48C]">
            Enterprise
          </Link>
          <Link href="/portal/attacker-simulation" className="hover:text-[#00C48C]">
            Attacker sim
          </Link>
          <Link href="/portal/compliance" className="hover:text-[#00C48C]">
            C-27 primer
          </Link>
          <Link href="/portal/settings" className="hover:text-[#00C48C]">
            Settings
          </Link>
          <PortalSignOut />
        </nav>
      </div>
    </header>
  );
}
