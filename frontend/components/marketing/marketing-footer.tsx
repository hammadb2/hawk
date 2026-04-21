"use client";

import Image from "next/image";
import Link from "next/link";

export function MarketingFooter() {
  return (
    <footer className="relative border-t border-white/5 bg-ink-950 px-6 py-14 sm:px-8">
      <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-10 lg:flex-row lg:items-center">
        <div className="flex items-center gap-4">
          <Image
            src="/hawk-wordmark.png"
            alt="HAWK"
            width={350}
            height={200}
            className="h-9 w-auto select-none"
          />
          <p className="text-xs text-ink-200">Built by AKB Studios.</p>
        </div>
        <nav className="flex flex-wrap items-center gap-x-8 gap-y-3 text-sm text-ink-100">
          <Link href="/privacy" className="transition-colors hover:text-ink-0">
            Privacy
          </Link>
          <Link href="/guarantee-terms" className="transition-colors hover:text-ink-0">
            Guarantee terms
          </Link>
          <Link href="/free-scan" className="transition-colors hover:text-ink-0">
            Free scan
          </Link>
          <Link href="/portal/login" className="transition-colors hover:text-ink-0">
            Client portal
          </Link>
        </nav>
        <p className="text-xs text-ink-300">
          HAWK Security. All rights reserved. {new Date().getFullYear()}.
        </p>
      </div>
    </footer>
  );
}
