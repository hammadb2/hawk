"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { authApi, type User } from "@/lib/api";

const TOKEN_KEY = "hawk_token";
const AUTH_COOKIE = "hawk_auth";
const COOKIE_MAX_AGE = 7 * 24 * 60 * 60; // 7 days

function setAuthCookie() {
  if (typeof document !== "undefined") {
    document.cookie = `${AUTH_COOKIE}=1; path=/; max-age=${COOKIE_MAX_AGE}; samesite=lax`;
  }
}

function clearAuthCookie() {
  if (typeof document !== "undefined") {
    document.cookie = `${AUTH_COOKIE}=; path=/; max-age=0`;
  }
}

interface AuthState {
  token: string | null;
  user: User | null;
  loading: boolean;
}

const AuthContext = createContext<{
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; first_name?: string; last_name?: string; company?: string; industry?: string; province?: string }) => Promise<void>;
  logout: () => void;
  setUser: (u: User | null) => void;
  refreshUser: () => Promise<void>;
} | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ token: null, user: null, loading: true });

  const refreshUser = useCallback(async () => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
    if (!t) {
      setState({ token: null, user: null, loading: false });
      return;
    }
    try {
      const user = await authApi.me(t);
      setState({ token: t, user, loading: false });
      setAuthCookie();
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      clearAuthCookie();
      setState({ token: null, user: null, loading: false });
    }
  }, []);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
    if (!t) {
      setState((s) => ({ ...s, loading: false }));
      return;
    }
    authApi
      .me(t)
      .then((user) => {
        setState({ token: t, user, loading: false });
        setAuthCookie();
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        clearAuthCookie();
        setState({ token: null, user: null, loading: false });
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token, user } = await authApi.login({ email, password });
    if (typeof window !== "undefined") {
      localStorage.setItem(TOKEN_KEY, access_token);
      setAuthCookie();
    }
    setState({ token: access_token, user, loading: false });
  }, []);

  const register = useCallback(
    async (data: {
      email: string;
      password: string;
      first_name?: string;
      last_name?: string;
      company?: string;
      industry?: string;
      province?: string;
    }) => {
      const { access_token, user } = await authApi.register(data);
      if (typeof window !== "undefined") {
        localStorage.setItem(TOKEN_KEY, access_token);
        setAuthCookie();
      }
      setState({ token: access_token, user, loading: false });
    },
    []
  );

  const logout = useCallback(() => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(TOKEN_KEY);
      clearAuthCookie();
    }
    setState({ token: null, user: null, loading: false });
  }, []);

  const setUser = useCallback((u: User | null) => {
    setState((s) => ({ ...s, user: u }));
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token: state.token,
        user: state.user,
        loading: state.loading,
        login,
        register,
        logout,
        setUser,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
