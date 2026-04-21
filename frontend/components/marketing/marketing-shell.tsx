"use client";

import type { ReactNode } from "react";
import { SmoothScroll } from "@/components/marketing/smooth-scroll";
import { MarketingNav } from "@/components/marketing/marketing-nav";
import { MarketingFooter } from "@/components/marketing/marketing-footer";

/**
 * Wraps every marketing page with the dark graphite canvas, ambient glow,
 * smooth scroll, nav, and footer. Scope is gated by html.marketing-route so
 * the portal and CRM remain on the light shell.
 */
export function MarketingShell({
  children,
  ambient = true,
}: {
  children: ReactNode;
  /**
   * Renders the hero-side ambient amber glow + grid. Default true. Turn off
   * on legal pages where the visual noise competes with long form text.
   */
  ambient?: boolean;
}) {
  return (
    <div className="relative min-h-dvh w-full overflow-x-hidden bg-ink-950 font-display text-ink-0 antialiased selection:bg-signal/40 selection:text-ink-950">
      <SmoothScroll />

      {ambient ? (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-[720px] bg-ink-vignette"
          />
          <div aria-hidden className="pointer-events-none absolute inset-0 grid-ink" />
          <div aria-hidden className="noise-overlay" />
        </>
      ) : null}

      <MarketingNav />

      <main className="relative z-10">{children}</main>

      <MarketingFooter />
    </div>
  );
}
