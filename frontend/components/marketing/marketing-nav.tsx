"use client";

import Image from "next/image";
import Link from "next/link";

/**
 * Sticky nav for every marketing page. Anchor links route to /#section so
 * they work from /privacy, /guarantee-terms, and /free-scan too.
 */
export function MarketingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-ink-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 sm:px-8">
        <Link href="/" className="group inline-flex items-center" title="HAWK" aria-label="HAWK home">
          <Image
            src="/hawk-wordmark.png"
            alt="HAWK"
            width={350}
            height={200}
            priority
            className="h-8 w-auto select-none"
          />
        </Link>
        <nav className="hidden items-center gap-8 md:flex">
          <Link href="/#regulatory" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Regulatory
          </Link>
          <Link href="/#how" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            How it works
          </Link>
          <Link href="/#guarantee" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Guarantee
          </Link>
          <Link href="/#pricing" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Pricing
          </Link>
          <Link href="/#certified" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Certification
          </Link>
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href="/portal/login"
            className="hidden text-sm font-medium text-ink-100 transition-colors hover:text-ink-0 sm:inline-flex"
          >
            Log in
          </Link>
          <Link
            href="/free-scan"
            className="inline-flex items-center gap-1.5 rounded-full bg-signal px-4 py-2 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400"
          >
            Free scan
          </Link>
        </div>
      </div>
    </header>
  );
}
