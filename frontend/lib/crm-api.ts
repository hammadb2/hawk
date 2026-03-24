/**
 * HAWK CRM API client. Mirrors the pattern in lib/api.ts.
 */

import type {
  Activity,
  CharlotteEmail,
  CharlotteStats,
  Client,
  Commission,
  CRMUser,
  CRMUserStats,
  DashboardStats,
  Prospect,
  ScoreboardEntry,
  Task,
} from "./crm-types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://hawk.akbstudios.com";

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<T> {
  const { token, ...init } = options;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (!(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : data.detail?.[0]?.msg || "Request failed";
    throw new Error(detail);
  }
  return data as T;
}

// Dashboard
export const crmDashboardApi = {
  getStats: (token: string) =>
    request<DashboardStats>("/api/crm/dashboard/stats", { token }),
};

// Prospects
export const crmProspectsApi = {
  list: (
    token: string,
    params: {
      stage?: string;
      source?: string;
      assigned_rep_id?: string;
      search?: string;
      page?: number;
      limit?: number;
    } = {}
  ) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
    return request<Prospect[]>(`/api/crm/prospects?${qs}`, { token });
  },
  get: (token: string, id: string) =>
    request<Prospect>(`/api/crm/prospects/${id}`, { token }),
  create: (token: string, body: Partial<Prospect>) =>
    request<Prospect>("/api/crm/prospects", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
  update: (token: string, id: string, body: Partial<Prospect>) =>
    request<Prospect>(`/api/crm/prospects/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
      token,
    }),
  moveStage: (
    token: string,
    id: string,
    stage: string,
    opts: { lost_reason?: string; note?: string } = {}
  ) =>
    request<Prospect>(`/api/crm/prospects/${id}/stage`, {
      method: "PUT",
      body: JSON.stringify({ stage, ...opts }),
      token,
    }),
  assign: (token: string, id: string, assigned_rep_id: string | null) =>
    request<Prospect>(`/api/crm/prospects/${id}/assign`, {
      method: "PUT",
      body: JSON.stringify({ assigned_rep_id }),
      token,
    }),
  convert: (token: string, id: string) =>
    request<Prospect>(`/api/crm/prospects/${id}/convert`, {
      method: "POST",
      body: JSON.stringify({}),
      token,
    }),
  importCSV: (token: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ created: number; skipped: number; errors: unknown[] }>(
      "/api/crm/prospects/import",
      { method: "POST", body: form, token }
    );
  },
  delete: (token: string, id: string) =>
    request<void>(`/api/crm/prospects/${id}`, { method: "DELETE", token }),
};

// Clients
export const crmClientsApi = {
  list: (
    token: string,
    params: { status?: string; churn_risk?: string; search?: string; page?: number } = {}
  ) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
    return request<Client[]>(`/api/crm/clients?${qs}`, { token });
  },
  get: (token: string, id: string) =>
    request<Client>(`/api/crm/clients/${id}`, { token }),
  update: (token: string, id: string, body: Partial<Client>) =>
    request<Client>(`/api/crm/clients/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
      token,
    }),
  markChurned: (token: string, id: string, reason?: string) =>
    request<Client>(`/api/crm/clients/${id}/churn`, {
      method: "POST",
      body: JSON.stringify({ reason }),
      token,
    }),
};

// Activities
export const crmActivitiesApi = {
  listForProspect: (token: string, prospectId: string) =>
    request<Activity[]>(`/api/crm/activities/prospect/${prospectId}`, { token }),
  create: (token: string, body: { prospect_id: string; activity_type: string; description?: string }) =>
    request<Activity>("/api/crm/activities", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
};

// Tasks
export const crmTasksApi = {
  list: (token: string, params: { completed?: boolean; prospect_id?: string } = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
    return request<Task[]>(`/api/crm/tasks?${qs}`, { token });
  },
  create: (token: string, body: Partial<Task>) =>
    request<Task>("/api/crm/tasks", { method: "POST", body: JSON.stringify(body), token }),
  update: (token: string, id: string, body: Partial<Task>) =>
    request<Task>(`/api/crm/tasks/${id}`, { method: "PUT", body: JSON.stringify(body), token }),
  complete: (token: string, id: string) =>
    request<Task>(`/api/crm/tasks/${id}/complete`, { method: "PUT", body: "{}", token }),
  delete: (token: string, id: string) =>
    request<void>(`/api/crm/tasks/${id}`, { method: "DELETE", token }),
};

// Team
export const crmTeamApi = {
  me: (token: string) => request<CRMUser>("/api/crm/team/me", { token }),
  list: (token: string) => request<CRMUserStats[]>("/api/crm/team", { token }),
  get: (token: string, id: string) =>
    request<CRMUserStats>(`/api/crm/team/${id}`, { token }),
  create: (token: string, body: {
    email: string; password: string; crm_role: string;
    first_name?: string; last_name?: string; monthly_target?: number; team_lead_id?: string;
  }) =>
    request<CRMUser>("/api/crm/team", { method: "POST", body: JSON.stringify(body), token }),
  update: (token: string, id: string, body: Partial<CRMUser> & { first_name?: string; last_name?: string }) =>
    request<CRMUser>(`/api/crm/team/${id}`, { method: "PUT", body: JSON.stringify(body), token }),
  deactivate: (token: string, id: string) =>
    request<CRMUser>(`/api/crm/team/${id}/deactivate`, { method: "PUT", body: "{}", token }),
};

// Scoreboard
export const crmScoreboardApi = {
  get: (token: string, period: "week" | "month" | "quarter" | "all" = "month") =>
    request<{ period: string; leaderboard: ScoreboardEntry[]; my_rank: number | null; total_reps: number }>(
      `/api/crm/scoreboard?period=${period}`,
      { token }
    ),
};

// Charlotte
export const crmCharlotteApi = {
  listEmails: (token: string, params: { status?: string; prospect_id?: string; page?: number } = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
    return request<CharlotteEmail[]>(`/api/crm/charlotte/emails?${qs}`, { token });
  },
  getStats: (token: string) => request<CharlotteStats>("/api/crm/charlotte/stats", { token }),
  createCampaign: (
    token: string,
    body: { targets: unknown[]; subject_template: string; body_template: string }
  ) =>
    request<{ queued: number }>("/api/crm/charlotte/campaign", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
};

// Commissions
export const crmCommissionsApi = {
  my: (token: string, paid?: boolean) => {
    const qs = paid !== undefined ? `?paid=${paid}` : "";
    return request<Commission[]>(`/api/crm/commissions/my${qs}`, { token });
  },
  list: (token: string, params: { crm_user_id?: string; paid?: boolean } = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
    return request<Commission[]>(`/api/crm/commissions?${qs}`, { token });
  },
  create: (token: string, body: {
    crm_user_id: string; client_id: string; commission_type: string;
    amount: number; period_start?: string; period_end?: string;
  }) =>
    request<Commission>("/api/crm/commissions", { method: "POST", body: JSON.stringify(body), token }),
  markPaid: (token: string, id: string) =>
    request<Commission>(`/api/crm/commissions/${id}/pay`, { method: "PUT", body: "{}", token }),
};

// Reports
export const crmReportsApi = {
  revenue: (token: string) => request<unknown>("/api/crm/reports/revenue", { token }),
  pipeline: (token: string) => request<unknown>("/api/crm/reports/pipeline", { token }),
  commissions: (token: string) => request<unknown>("/api/crm/reports/commissions", { token }),
};
