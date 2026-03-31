"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { Profile } from "@/lib/crm/types";

type CrmAuthContextValue = {
  authReady: boolean;
  session: import("@supabase/supabase-js").Session | null;
  profile: Profile | null;
  refreshProfile: () => Promise<void>;
  signOut: () => Promise<void>;
};

const CrmAuthContext = createContext<CrmAuthContextValue | null>(null);

const AUTH_READY_TIMEOUT_MS = 5000;

export function CrmAuthProvider({ children }: { children: React.ReactNode }) {
  const supabase = useMemo(() => createClient(), []);
  const [authReady, setAuthReady] = useState(false);
  const [session, setSession] = useState<import("@supabase/supabase-js").Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

  const loadProfile = useCallback(
    async (userId: string) => {
      const { data, error } = await supabase.from("profiles").select("*").eq("id", userId).maybeSingle();
      if (error || !data) {
        setProfile(null);
        return;
      }
      setProfile(data as Profile);
    },
    [supabase]
  );

  const refreshProfile = useCallback(async () => {
    const { data } = await supabase.auth.getUser();
    if (data.user) await loadProfile(data.user.id);
    else setProfile(null);
  }, [loadProfile, supabase]);

  useEffect(() => {
    let done = false;
    const t = window.setTimeout(() => {
      if (!done) {
        done = true;
        setAuthReady(true);
      }
    }, AUTH_READY_TIMEOUT_MS);

    supabase.auth
      .getSession()
      .then(({ data: { session: s } }) => {
        if (!done) {
          done = true;
          clearTimeout(t);
          setSession(s);
          setAuthReady(true);
          if (s?.user) void loadProfile(s.user.id);
        }
      })
      .catch(() => {
        if (!done) {
          done = true;
          clearTimeout(t);
          setAuthReady(true);
        }
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      if (s?.user) void loadProfile(s.user.id);
      else setProfile(null);
    });

    return () => {
      clearTimeout(t);
      subscription.unsubscribe();
    };
  }, [loadProfile, supabase]);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut({ scope: "local" });
    setSession(null);
    setProfile(null);
    window.location.href = "/crm/login";
  }, [supabase]);

  const value = useMemo(
    () => ({
      authReady,
      session,
      profile,
      refreshProfile,
      signOut,
    }),
    [authReady, session, profile, refreshProfile, signOut]
  );

  return <CrmAuthContext.Provider value={value}>{children}</CrmAuthContext.Provider>;
}

export function useCrmAuth() {
  const ctx = useContext(CrmAuthContext);
  if (!ctx) throw new Error("useCrmAuth must be used within CrmAuthProvider");
  return ctx;
}
