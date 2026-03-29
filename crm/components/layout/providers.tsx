"use client";

import { createContext, useContext, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { getSupabaseClient } from "@/lib/supabase";
import { useCRMStore } from "@/store/crm-store";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import type { CRMUser } from "@/types/crm";

// Default true: data hooks must not block forever if context mismatches (Next.js boundaries).
// The CRM layout + middleware already guarantee auth before these pages mount.
const AuthReadyContext = createContext<boolean>(true);

export function useAuthReady(): boolean {
  return useContext(AuthReadyContext);
}

interface ProvidersProps {
  children: ReactNode;
  initialUser?: CRMUser | null;
}

export function Providers({ children, initialUser }: ProvidersProps) {
  const setUser = useCRMStore((s) => s.setUser);
  // Server layout already ran getUser() + loaded profile — safe to render immediately.
  // Waiting on client getSession() alone caused hard-refresh hangs (spinner forever, no shell/sign-out).
  const [authReady, setAuthReady] = useState(() => Boolean(initialUser));

  useLayoutEffect(() => {
    if (initialUser) {
      setUser(initialUser);
    }
  }, [initialUser, setUser]);

  useEffect(() => {
    const supabase = getSupabaseClient();
    let cancelled = false;
    const AUTH_SESSION_TIMEOUT_MS = 5000;

    // For routes without initialUser (future use): unblock after timeout or when session resolves.
    const timeoutId = window.setTimeout(() => {
      if (!cancelled) setAuthReady(true);
    }, AUTH_SESSION_TIMEOUT_MS);

    supabase.auth
      .getSession()
      .then(() => {
        window.clearTimeout(timeoutId);
        if (!cancelled) setAuthReady(true);
      })
      .catch(() => {
        window.clearTimeout(timeoutId);
        if (!cancelled) setAuthReady(true);
      });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (!cancelled) setAuthReady(true);

        if (event === "SIGNED_OUT") {
          setUser(null);
          window.location.href = "/login";
          return;
        }

        if (!session) return;

        if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED") {
          const { data: userProfile } = await supabase
            .from("users")
            .select("id, name, email, role, status, team_lead_id, whatsapp_number, team_lead:team_lead_id(id, name, email, role)")
            .eq("id", session.user.id)
            .single();

          if (userProfile) {
            setUser(userProfile as unknown as CRMUser);
          }
        }
      }
    );

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      subscription.unsubscribe();
    };
  }, [setUser]);

  const handleEmergencySignOut = async () => {
    const supabase = getSupabaseClient();
    try {
      await supabase.auth.signOut({ scope: "local" });
    } catch {
      // still leave the app
    }
    window.location.href = "/login";
  };

  // Without initialUser, wait until client session is known (or timeout).
  if (!authReady) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-6 h-screen px-4"
        style={{ background: "#07060C" }}
      >
        <div className="w-8 h-8 rounded-full border-2 border-purple-500 border-t-transparent animate-spin" />
        <p className="text-xs text-text-dim text-center max-w-xs">
          If this takes too long, you can sign out and try again.
        </p>
        <Button type="button" variant="secondary" size="sm" className="text-xs" onClick={() => void handleEmergencySignOut()}>
          Sign out
        </Button>
      </div>
    );
  }

  return (
    <AuthReadyContext.Provider value={authReady}>
      <TooltipProvider delayDuration={300}>
        {children}
        <Toaster />
      </TooltipProvider>
    </AuthReadyContext.Provider>
  );
}
