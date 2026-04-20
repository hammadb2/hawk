"use client";

/**
 * Universal "live refresh" signal used across the whole app.
 *
 * A single monotonically-increasing counter that ticks up whenever we decide
 * the UI should re-fetch its server data:
 *
 *   - window regains focus
 *   - tab becomes visible again
 *   - network comes back online
 *   - a background interval fires (default 60s while visible)
 *   - someone explicitly calls ``triggerRefreshSignal()``
 *
 * The signal is implemented as a module-level counter + a set of listeners,
 * so it's visible to every hook in every tree without needing a provider.
 * That means a single ``<LiveRefreshBeacon />`` mounted in the root layout is
 * enough to keep the whole app live — no per-page wiring required.
 */
import { useEffect, useRef, useState } from "react";

type Listener = (n: number) => void;

let signalCounter = 0;
const listeners = new Set<Listener>();

/** Collapse rapid-fire emits (e.g. focus + visibilitychange both firing on tab return) into one. */
const EMIT_DEBOUNCE_MS = 200;
let lastEmitAt = 0;

function emit() {
  const now = typeof performance !== "undefined" ? performance.now() : Date.now();
  if (now - lastEmitAt < EMIT_DEBOUNCE_MS) return;
  lastEmitAt = now;
  signalCounter += 1;
  listeners.forEach((fn) => {
    try {
      fn(signalCounter);
    } catch {
      // Ignore listener errors so one bad page doesn't break the rest.
    }
  });
}

/** Manually kick a refresh (e.g. after a mutation that wasn't covered by Realtime). */
export function triggerRefreshSignal() {
  emit();
}

/** Subscribe imperatively (outside React). Returns an unsubscribe fn. */
export function subscribeRefreshSignal(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getRefreshSignal(): number {
  return signalCounter;
}

/** React hook — re-renders whenever the signal ticks. */
export function useRefreshSignal(): number {
  const [n, setN] = useState(signalCounter);
  useEffect(() => {
    return subscribeRefreshSignal(setN);
  }, []);
  return n;
}

/**
 * ``useLiveEffect`` behaves like ``useEffect(cb, deps)`` but also re-runs
 * whenever the refresh signal ticks. Use this as a drop-in replacement for
 * ``useEffect`` on any data-fetch effect to get live auto-refresh.
 */
export function useLiveEffect(effect: () => void | (() => void), deps: ReadonlyArray<unknown>) {
  const signal = useRefreshSignal();
  const depsRef = useRef(deps);
  depsRef.current = deps;
  useEffect(() => {
    return effect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, signal]);
}

// ---------------------------------------------------------------------------
// Beacon — wire focus / visibility / interval / online events to the signal.
// Installed as a module-level side effect when imported in the browser so even
// without <LiveRefreshBeacon /> things still work.
// ---------------------------------------------------------------------------

let beaconInstalled = false;
const DEFAULT_INTERVAL_MS = 60_000;

export function installRefreshBeacon(intervalMs: number = DEFAULT_INTERVAL_MS) {
  if (typeof window === "undefined" || beaconInstalled) return;
  beaconInstalled = true;

  const onFocus = () => emit();
  const onVisible = () => {
    if (document.visibilityState === "visible") emit();
  };
  const onOnline = () => emit();

  let timer: ReturnType<typeof setInterval> | null = null;
  const startTimer = () => {
    if (timer) return;
    timer = setInterval(() => {
      if (document.visibilityState === "visible") emit();
    }, intervalMs);
  };
  const stopTimer = () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  };

  window.addEventListener("focus", onFocus);
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("online", onOnline);
  startTimer();

  // Expose a global escape hatch for ad-hoc triggers from non-React code.
  (window as unknown as { __hawkRefresh?: () => void }).__hawkRefresh = triggerRefreshSignal;

  // Stop the timer if the document goes away (SPA nav shouldn't hit this).
  window.addEventListener("beforeunload", () => {
    window.removeEventListener("focus", onFocus);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onOnline);
    stopTimer();
  });
}
