"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getSupabaseClient } from "@/lib/supabase";
import { useCRMStore } from "@/store/crm-store";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { CRMUser } from "@/types/crm";

const AuthReadyContext = createContext(false);
export const useAuthReady = () => useContext(AuthReadyContext);

interface ProvidersProps {
  children: ReactNode;
  initialUser?: CRMUser | null;
}

export function Providers({ children, initialUser }: ProvidersProps) {
  const setUser = useCRMStore((s) => s.setUser);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    if (initialUser) {
      setUser(initialUser);
    }
  }, [initialUser, setUser]);

  useEffect(() => {
    const supabase = getSupabaseClient();
    let cancelled = false;
    const AUTH_SESSION_TIMEOUT_MS = 5000;

    // getSession() resolves once Supabase has restored the session from
    // cookies. If the network stalls, still unblock the shell after a cap.
    const timeoutId = window.setTimeout(() => {
      if (!cancelled) setAuthReady(true);
    }, AUTH_SESSION_TIMEOUT_MS);

    supabase.auth.getSession().then(() => {
      window.clearTimeout(timeoutId);
      if (!cancelled) setAuthReady(true);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        setAuthReady(true);

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

  // Don't render anything until auth state is known — prevents data-fetching
  // components from firing unauthenticated queries on page reload.
  if (!authReady) {
    return (
      <div className="flex items-center justify-center h-screen" style={{ background: "#07060C" }}>
        <div className="w-8 h-8 rounded-full border-2 border-purple-500 border-t-transparent animate-spin" />
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
