"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { portalApi } from "@/lib/api";
import { portal } from "@/lib/portal-ui";

/** Login + OAuth callback only — no session/bootstrap logic here. */
function isPortalAuthPublicPath(pathname: string | null): boolean {
  if (!pathname?.startsWith("/portal")) return false;
  if (pathname === "/portal/login") return true;
  if (pathname.startsWith("/portal/auth")) return true;
  return false;
}

/** Billing / Stripe return: run bootstrap when signed in, but do not enforce paid access here. */
function isPortalBillingPath(pathname: string | null): boolean {
  if (!pathname) return false;
  return pathname.startsWith("/portal/billing") || pathname.startsWith("/portal/return");
}

function buildNextForLogin(pathname: string, searchParams: URLSearchParams): string {
  const q = searchParams.toString();
  return pathname + (q ? `?${q}` : "");
}

function isPaidClient(row: { billing_status?: string | null; mrr_cents?: number | null } | null): boolean {
  if (!row) return false;
  if (row.billing_status === "active") return true;
  return Number(row.mrr_cents ?? 0) >= 19900;
}

/**
 * Account-first: after sign-in, unpaid users only use /portal/billing until subscription is active.
 */
export function PortalGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [ready, setReady] = useState(() => isPortalAuthPublicPath(pathname));

  useEffect(() => {
    if (isPortalAuthPublicPath(pathname)) {
      setReady(true);
      return;
    }

    let cancelled = false;
    (async () => {
      setReady(false);
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        const next = buildNextForLogin(pathname, searchParams);
        router.replace(`/portal/login?next=${encodeURIComponent(next)}`);
        return;
      }

      try {
        await portalApi.bootstrap(session.access_token);
      } catch (e) {
        console.error("portal bootstrap:", e);
      }

      if (cancelled) return;

      if (isPortalBillingPath(pathname)) {
        setReady(true);
        return;
      }

      const { data: cpp } = await supabase
        .from("client_portal_profiles")
        .select("client_id")
        .eq("user_id", session.user.id)
        .maybeSingle();

      if (cancelled) return;

      if (!cpp?.client_id) {
        setReady(true);
        return;
      }

      const { data: client } = await supabase
        .from("clients")
        .select("billing_status,mrr_cents")
        .eq("id", cpp.client_id)
        .maybeSingle();

      if (cancelled) return;

      if (!isPaidClient(client)) {
        router.replace("/portal/billing");
        return;
      }

      setReady(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [pathname, router, searchParams]);

  if (!ready) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-ink-0">
        <div className={portal.spinner} />
      </div>
    );
  }

  return <>{children}</>;
}
