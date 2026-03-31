"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { Profile } from "@/lib/crm/types";

type CrmAuthContextValue = {
  authReady: boolean;
  /** True after we finished loading `profiles` for the current session (or confirmed no session). */
  profileFetched: boolean;
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
  const [profileFetched, setProfileFetched] = useState(false);
  const [session, setSession] = useState<import("@supabase/supabase-js").Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

  const loadProfile = useCallback(
    async (userId: string) => {
      const { data, error } = await supabase.from("profiles").select("*").eq("id", userId).maybeSingle();
      if (error) {
        console.error("[CRM auth] profiles select failed:", error.message, error.code, error.details ?? "");
        setProfile(null);
        return;
      }
      if (!data) {
        console.warn(
          "[CRM auth] No row in public.profiles for this user. id must equal auth.users.id:",
          userId
        );
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
    setProfileFetched(true);
  }, [loadProfile, supabase]);

  useEffect(() => {
    let done = false;
    const t = window.setTimeout(() => {
      if (!done) {
        done = true;
        setAuthReady(true);
        setProfileFetched(true);
      }
    }, AUTH_READY_TIMEOUT_MS);

    supabase.auth
      .getSession()
      .then(async ({ data: { session: s } }) => {
        if (!done) {
          done = true;
          clearTimeout(t);
          setSession(s);
          setAuthReady(true);
          if (s?.user) {
            await loadProfile(s.user.id);
            setProfileFetched(true);
          } else {
            setProfile(null);
            setProfileFetched(true);
          }
        }
      })
      .catch((err) => {
        console.error("[CRM auth] getSession failed:", err);
        if (!done) {
          done = true;
          clearTimeout(t);
          setAuthReady(true);
          setProfileFetched(true);
        }
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, s) => {
      setSession(s);
      if (s?.user) {
        await loadProfile(s.user.id);
        setProfileFetched(true);
      } else {
        setProfile(null);
        setProfileFetched(true);
      }
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
    setProfileFetched(true);
    window.location.href = "/crm/login";
  }, [supabase]);

  const value = useMemo(
    () => ({
      authReady,
      profileFetched,
      session,
      profile,
      refreshProfile,
      signOut,
    }),
    [authReady, profileFetched, session, profile, refreshProfile, signOut]
  );

  return <CrmAuthContext.Provider value={value}>{children}</CrmAuthContext.Provider>;
}

export function useCrmAuth() {
  const ctx = useContext(CrmAuthContext);
  if (!ctx) throw new Error("useCrmAuth must be used within CrmAuthProvider");
  return ctx;
}
