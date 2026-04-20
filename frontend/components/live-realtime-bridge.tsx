"use client";

/**
 * Bridges Supabase Realtime events on a broad set of pipeline / CRM tables to
 * the universal refresh signal, so any row-level INSERT/UPDATE/DELETE triggers
 * an immediate refetch across the whole app (SWR + Server Components).
 *
 * The prospects-specific hook (useProspectsRealtimeSubscription) still runs on
 * the prospects page for targeted SWR invalidation — this bridge is the
 * catch-all for every other live-data table.
 */
import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { triggerRefreshSignal } from "@/lib/hooks/use-refresh-signal";

/** Tables worth listening to across the app. Missing tables are silently ignored by Realtime. */
const LIVE_TABLES = [
  "prospects",
  "clients",
  "activities",
  "aria_lead_inventory",
  "aria_pipeline_runs",
  "aria_messages",
  "aria_conversations",
  "crm_prospect_scans",
  "scans",
  "findings",
  "client_domain_scans",
  "client_portal_profiles",
  "notifications",
  "suppressions",
  "crm_commissions",
  "crm_settings",
] as const;

export function LiveRealtimeBridge() {
  useEffect(() => {
    const supabase = createClient();
    let channel = supabase.channel("hawk-live-refresh");
    for (const table of LIVE_TABLES) {
      channel = channel.on(
        "postgres_changes",
        { event: "*", schema: "public", table },
        () => {
          triggerRefreshSignal();
        }
      ) as typeof channel;
    }
    channel.subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, []);
  return null;
}
