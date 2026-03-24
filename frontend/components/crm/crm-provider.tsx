"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { crmTeamApi } from "@/lib/crm-api";
import { useAuth } from "@/components/providers/auth-provider";
import type { CRMUser } from "@/lib/crm-types";

interface CRMContextType {
  crmUser: CRMUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  hasFullVisibility: boolean;
  isTeamLead: boolean;
}

const CRMContext = createContext<CRMContextType | null>(null);

export function CRMProvider({ children }: { children: React.ReactNode }) {
  const { token, user } = useAuth();
  const router = useRouter();
  const [crmUser, setCrmUser] = useState<CRMUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const cu = await crmTeamApi.me(token);
      setCrmUser(cu);
    } catch {
      setCrmUser(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (user && token) {
      refresh();
    } else if (!user) {
      setLoading(false);
    }
  }, [user, token, refresh]);

  const hasFullVisibility = crmUser?.crm_role === "ceo" || crmUser?.crm_role === "head_of_sales";
  const isTeamLead = crmUser?.crm_role === "team_lead";

  return (
    <CRMContext.Provider value={{ crmUser, loading, refresh, hasFullVisibility, isTeamLead }}>
      {children}
    </CRMContext.Provider>
  );
}

export function useCRM() {
  const ctx = useContext(CRMContext);
  if (!ctx) throw new Error("useCRM must be used within CRMProvider");
  return ctx;
}
