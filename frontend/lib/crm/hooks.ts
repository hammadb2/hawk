"use client";

import { useEffect } from "react";
import useSWR, { mutate as swrMutate } from "swr";
import { createClient } from "@/lib/supabase/client";
import type { CrmClientRow, Profile, Prospect, ProspectPipelineStatus } from "@/lib/crm/types";

const supabase = createClient();

export type ProspectsListFilter = "all" | "active" | ProspectPipelineStatus;

export function prospectsSwrKey(filter: ProspectsListFilter) {
  return filter === "all" ? ("prospects" as const) : (["prospects", filter] as const);
}

async function fetchProspectsList(filter: ProspectsListFilter): Promise<Prospect[]> {
  let q = supabase.from("prospects").select("*");
  if (filter === "active") {
    q = q.or("pipeline_status.is.null,pipeline_status.neq.suppressed");
  } else if (filter !== "all") {
    q = q.eq("pipeline_status", filter);
  }
  const { data, error } = await q
    .order("lead_score", { ascending: false, nullsFirst: false })
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data as Prospect[]) ?? [];
}

export function useProspectsList(pipelineFilter: ProspectsListFilter) {
  return useSWR(prospectsSwrKey(pipelineFilter), () => fetchProspectsList(pipelineFilter), {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
}

/** Alias for pipeline — shares the `prospects` cache when the list is unfiltered. */
export function useProspects() {
  return useProspectsList("all");
}

export function useClients() {
  return useSWR(
    "clients",
    async () => {
      const { data, error } = await supabase
        .from("clients")
        .select(
          "id, prospect_id, company_name, domain, plan, mrr_cents, stripe_customer_id, closing_rep_id, status, close_date, created_at, monitored_domains"
        )
        .order("close_date", { ascending: false });
      if (error) throw error;
      return (data as CrmClientRow[]) ?? [];
    },
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );
}

export function useProfiles() {
  return useSWR(
    "profiles",
    async () => {
      const { data, error } = await supabase
        .from("profiles")
        .select("id,full_name,email,role,health_score")
        .limit(200);
      if (error) throw error;
      return (data as Pick<Profile, "id" | "full_name" | "email" | "role" | "health_score">[]) ?? [];
    },
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );
}

export type TeamDirectoryState = { rows: Profile[]; tlNames: Record<string, string> };

export function useTeamDirectory() {
  return useSWR(
    ["crm", "team-directory"] as const,
    async (): Promise<TeamDirectoryState> => {
      const { data, error } = await supabase
        .from("profiles")
        .select(
          "id, email, full_name, role, team_lead_id, status, monthly_close_target, last_close_at, created_at, onboarding_completed_at, whatsapp_number"
        )
        .in("role", ["sales_rep", "team_lead"])
        .order("full_name", { ascending: true, nullsFirst: false });
      if (error) throw error;
      const list = (data ?? []) as Profile[];
      const tlIds = Array.from(new Set(list.map((p) => p.team_lead_id).filter(Boolean) as string[]));
      const tlNames: Record<string, string> = {};
      if (tlIds.length) {
        const { data: tls, error: e2 } = await supabase.from("profiles").select("id, full_name, email").in("id", tlIds);
        if (e2) throw e2;
        for (const t of tls ?? []) {
          tlNames[t.id] = t.full_name ?? t.email ?? t.id.slice(0, 8);
        }
      }
      return { rows: list, tlNames };
    },
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );
}

export function revalidateTeamDirectory() {
  return swrMutate(["crm", "team-directory"] as const, undefined, { revalidate: true });
}

export function revalidateProfilesCache() {
  return swrMutate("profiles", undefined, { revalidate: true });
}

export function useHotLeads(enabled: boolean) {
  return useSWR(
    enabled ? (["prospects", "hot"] as const) : null,
    async () => {
      const { data, error } = await supabase
        .from("prospects")
        .select("*")
        .eq("is_hot", true)
        .order("last_activity_at", { ascending: false })
        .limit(8);
      if (error) throw error;
      return (data as Prospect[]) ?? [];
    },
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );
}

export function revalidateProspectCaches() {
  return swrMutate(
    (key) => key === "prospects" || (Array.isArray(key) && key[0] === "prospects"),
    undefined,
    { revalidate: true }
  );
}

export function revalidateClientsCache() {
  return swrMutate("clients", undefined, { revalidate: true });
}

/** Revalidates SWR when prospects or clients change (INSERT/UPDATE). */
export function useProspectsRealtimeSubscription(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const channel = supabase
      .channel("crm-prospects-clients-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "prospects" }, () => {
        void revalidateProspectCaches();
      })
      .on("postgres_changes", { event: "UPDATE", schema: "public", table: "prospects" }, () => {
        void revalidateProspectCaches();
      })
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "clients" }, () => {
        void revalidateClientsCache();
      })
      .on("postgres_changes", { event: "UPDATE", schema: "public", table: "clients" }, () => {
        void revalidateClientsCache();
      })
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [enabled]);
}
