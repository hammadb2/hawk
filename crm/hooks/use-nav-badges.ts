"use client";

import { useState, useEffect, useCallback } from "react";
import { getSupabaseClient } from "@/lib/supabase";
import { charlotteApi } from "@/lib/api";
import type { CRMUser } from "@/types/crm";

/** Counts for HAWK CRM Master Spec §03 nav badges (sidebar + mobile). */
export interface NavBadgeCounts {
  /** Prospects in active stages with no touch in 14+ days (spec: red pipeline stale). */
  overduePipeline: number;
  /** New-stage prospects created since local midnight. */
  uncontactedToday: number;
  /** Active clients with high/critical churn risk. */
  churnRisk: number;
  /** Charlotte emails sent today (CEO/HoS); null if API unavailable. */
  charlotteSentToday: number | null;
  /** Reps / team leads marked at_risk. */
  flaggedReps: number;
  /** Tickets not yet resolved (CEO console). */
  openTickets: number;
}

const DEFAULTS: NavBadgeCounts = {
  overduePipeline: 0,
  uncontactedToday: 0,
  churnRisk: 0,
  charlotteSentToday: null,
  flaggedReps: 0,
  openTickets: 0,
};

function startOfLocalDayIso(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function fourteenDaysAgoIso(): string {
  return new Date(Date.now() - 14 * 86400000).toISOString();
}

export function useNavBadges(user: CRMUser | null): NavBadgeCounts {
  const [counts, setCounts] = useState<NavBadgeCounts>(DEFAULTS);

  const refresh = useCallback(async () => {
    if (!user) return;
    const sb = getSupabaseClient();
    const role = user.role;

    try {
      const [staleRes, newTodayRes, churnRes] = await Promise.all([
        sb
          .from("prospects")
          .select("id", { count: "exact", head: true })
          .neq("stage", "lost")
          .neq("stage", "closed_won")
          .lt("last_activity_at", fourteenDaysAgoIso()),
        sb
          .from("prospects")
          .select("id", { count: "exact", head: true })
          .eq("stage", "new")
          .gte("created_at", startOfLocalDayIso()),
        sb
          .from("clients")
          .select("id", { count: "exact", head: true })
          .eq("status", "active")
          .in("churn_risk_score", ["high", "critical"]),
      ]);

      let charlotteSentToday: number | null = null;
      let flaggedReps = 0;
      let openTickets = 0;

      if (role === "ceo" || role === "hos") {
        const [{ count: atRisk }, charRes] = await Promise.all([
          sb
            .from("users")
            .select("id", { count: "exact", head: true })
            .eq("status", "at_risk")
            .in("role", ["rep", "team_lead"]),
          charlotteApi.stats(),
        ]);
        flaggedReps = atRisk ?? 0;
        if (charRes.success && charRes.data) {
          charlotteSentToday = charRes.data.sent_today ?? 0;
        }
      }

      if (role === "ceo") {
        const { count: open } = await sb
          .from("tickets")
          .select("id", { count: "exact", head: true })
          .in("status", ["received", "in_progress", "monitoring"]);
        openTickets = open ?? 0;
      }

      setCounts({
        overduePipeline: staleRes.count ?? 0,
        uncontactedToday: newTodayRes.count ?? 0,
        churnRisk: churnRes.count ?? 0,
        charlotteSentToday,
        flaggedReps,
        openTickets,
      });
    } catch {
      setCounts(DEFAULTS);
    }
  }, [user]);

  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 120_000);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(t);
      window.removeEventListener("focus", onFocus);
    };
  }, [refresh]);

  return counts;
}
