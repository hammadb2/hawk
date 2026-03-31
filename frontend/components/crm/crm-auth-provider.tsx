"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { AuthChangeEvent, Session, SupabaseClient } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";
import type { Profile } from "@/lib/crm/types";

type CrmAuthContextValue = {
  authReady: boolean;
  /** True after we finished loading `profiles` for the current session (or confirmed no session). */
  profileFetched: boolean;
  session: Session | null;
  profile: Profile | null;
  refreshProfile: () => Promise<void>;
  signOut: () => Promise<void>;
};

const CrmAuthContext = createContext<CrmAuthContextValue | null>(null);

const AUTH_READY_TIMEOUT_MS = 8000;

/** Retries when Navigator Lock API reports stolen / released locks (parallel getSession races). */
async function getSessionWithRetry(supabase: SupabaseClient) {
  const maxAttempts = 3;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const { data, error } = await supabase.auth.getSession();
      if (error) throw error;
      return { data, error: null as null };
    } catch (e) {
      const msg = String(e);
      const retryable =
        msg.includes("lock") ||
        msg.includes("Lock") ||
        msg.includes("stole") ||
        msg.includes("NavigatorLock") ||
        msg.includes("released");
      if (attempt < maxAttempts && retryable) {
        await new Promise((r) => setTimeout(r, 100 * attempt));
        continue;
      }
      console.error("[CRM auth] getSession failed:", e);
      return { data: { session: null as Session | null }, error: e as Error };
    }
  }
  return { data: { session: null as Session | null }, error: null as null };
}

export function CrmAuthProvider({ children }: { children: React.ReactNode }) {
  const supabase = useMemo(() => createClient(), []);
  const [authReady, setAuthReady] = useState(false);
  const [profileFetched, setProfileFetched] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
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
    let cancelled = false;
    let timeoutId: number | undefined;
    let subscription: { unsubscribe: () => void } | null = null;

    timeoutId = window.setTimeout(() => {
      if (!cancelled) {
        setAuthReady(true);
        setProfileFetched(true);
      }
    }, AUTH_READY_TIMEOUT_MS);

    void (async () => {
      const { data: sessionData } = await getSessionWithRetry(supabase);
      if (cancelled) return;

      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
        timeoutId = undefined;
      }

      const s = sessionData.session;
      setSession(s ?? null);
      setAuthReady(true);
      if (s?.user) {
        await loadProfile(s.user.id);
      } else {
        setProfile(null);
      }
      setProfileFetched(true);

      const {
        data: { subscription: sub },
      } = supabase.auth.onAuthStateChange(async (event: AuthChangeEvent, newSession: Session | null) => {
        if (cancelled) return;
        if (event === "INITIAL_SESSION") return;
        setSession(newSession);
        if (newSession?.user) {
          await loadProfile(newSession.user.id);
        } else {
          setProfile(null);
        }
        setProfileFetched(true);
      });
      subscription = sub;
    })();

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) clearTimeout(timeoutId);
      subscription?.unsubscribe();
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
