"use client";

/**
 * Mounted at the top of each route tree (CRM, portal, marketing/dashboard).
 *
 * Installs the universal refresh-signal beacon and bridges the signal to:
 *   - ``router.refresh()`` so Next.js Server Components refetch
 *   - ``swrMutate`` so all SWR caches revalidate on focus/visibility/interval
 *
 * The result: any page that uses ``useSWR``, ``useLiveEffect``, or Server
 * Components picks up fresh data without needing per-page wiring.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { mutate as swrMutate } from "swr";
import { installRefreshBeacon, subscribeRefreshSignal } from "@/lib/hooks/use-refresh-signal";

export function LiveRefreshBeacon() {
  const router = useRouter();
  useEffect(() => {
    installRefreshBeacon();
    return subscribeRefreshSignal(() => {
      try {
        router.refresh();
      } catch {
        // Router may not be mounted yet during early hydration.
      }
      try {
        // Revalidate every SWR key (predicate returns true for all).
        void swrMutate(() => true, undefined, { revalidate: true });
      } catch {
        // SWR mutate is best-effort; ignore errors.
      }
    });
  }, [router]);
  return null;
}
