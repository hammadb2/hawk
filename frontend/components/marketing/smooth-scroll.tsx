"use client";

import { useEffect } from "react";
import Lenis from "lenis";

/**
 * Mount this once inside a marketing page. It also toggles <html class="marketing-route">
 * for the duration the component is mounted, so the page canvas is graphite and the
 * scrollbar styling matches. The CRM/portal stays light because it doesn't mount this.
 */
export function SmoothScroll() {
  useEffect(() => {
    const html = document.documentElement;
    html.classList.add("marketing-route");

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let lenis: Lenis | null = null;
    let rafId = 0;

    if (!prefersReduced) {
      lenis = new Lenis({
        duration: 1.15,
        easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        smoothWheel: true,
        wheelMultiplier: 1,
        touchMultiplier: 1.2,
      });

      const raf = (time: number) => {
        lenis?.raf(time);
        rafId = requestAnimationFrame(raf);
      };
      rafId = requestAnimationFrame(raf);
    }

    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      lenis?.destroy();
      html.classList.remove("marketing-route");
    };
  }, []);

  return null;
}
