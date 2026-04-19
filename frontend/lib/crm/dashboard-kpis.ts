import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

export type CrmDashboardKpiPayload = {
  prospects_by_stage: Record<string, number>;
  active_clients_count: number;
  mrr_total_cents: number;
  calls_booked_today: number;
  emails_sent_today: number;
  emails_replied_today: number;
  hot_leads_count: number;
  closes_mtd: number;
  pipeline_open_dollars: number;
  stale_48h_open: number;
};

export async function fetchCrmDashboardKpis(
  accessToken: string,
  dayStartIso: string,
  monthStartIso: string
): Promise<CrmDashboardKpiPayload> {
  const u = new URL(`${CRM_API_BASE_URL}/api/crm/dashboard/kpis`);
  u.searchParams.set("day_start", dayStartIso);
  u.searchParams.set("month_start", monthStartIso);
  const res = await fetch(u.toString(), {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `KPI fetch failed (${res.status})`);
  }
  return (await res.json()) as CrmDashboardKpiPayload;
}
