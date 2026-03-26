"use client";

import { useEffect, type ReactNode } from "react";
import { createClient } from "@/lib/supabase";
import { useCRMStore } from "@/store/crm-store";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { CRMUser } from "@/types/crm";

interface ProvidersProps {
  children: ReactNode;
  initialUser?: CRMUser | null;
}

export function Providers({ children, initialUser }: ProvidersProps) {
  const setUser = useCRMStore((s) => s.setUser);

  useEffect(() => {
    if (initialUser) {
      setUser(initialUser);
    }
  }, [initialUser, setUser]);

  useEffect(() => {
    const supabase = createClient();

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (event === "SIGNED_OUT" || !session) {
          setUser(null);
          window.location.href = "/login";
          return;
        }

        if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED") {
          const { data: userProfile } = await supabase
            .from("users")
            .select("*, team_lead:team_lead_id(id, name, email, role)")
            .eq("id", session.user.id)
            .single();

          if (userProfile) {
            setUser(userProfile as CRMUser);
          }
        }
      }
    );

    return () => {
      subscription.unsubscribe();
    };
  }, [setUser]);

  return (
    <TooltipProvider delayDuration={300}>
      {children}
      <Toaster />
    </TooltipProvider>
  );
}
