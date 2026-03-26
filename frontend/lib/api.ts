/**
 * HAWK API client. All requests use JSON and optional Bearer token.
 * Defaults to production; set NEXT_PUBLIC_API_URL=http://localhost:8000 for local dev.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://hawk.akbstudios.com";

export type ApiError = { detail: string | { msg: string }[] };

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<T> {
  const { token, ...init } = options;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.detail?.[0]?.msg || "Request failed";
    throw new Error(detail);
  }
  return data as T;
}

// Auth
export const authApi = {
  register: (body: { email: string; password: string; first_name?: string; last_name?: string; company?: string; industry?: string; province?: string }) =>
    request<{ access_token: string; user: User }>("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body: { email: string; password: string }) =>
    request<{ access_token: string; user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  me: (token: string) => request<User>("/api/auth/me", { token }),
  forgotPassword: (body: { email: string }) =>
    request<{ message: string }>("/api/auth/forgot-password", { method: "POST", body: JSON.stringify(body) }),
  resetPassword: (body: { token: string; new_password: string }) =>
    request<{ message: string }>("/api/auth/reset-password", { method: "POST", body: JSON.stringify(body) }),
};

// Scans
export const scansApi = {
  start: (body: { domain: string }, token: string) =>
    request<{ scan_id: string; domain: string; status: string; score?: number; grade?: string }>("/api/scan", { method: "POST", body: JSON.stringify(body), token }),
  /** Public scan (no auth). For gate/lead capture. Returns real grade/score. */
  startPublic: (body: { domain: string }) =>
    request<{ domain: string; status: string; score?: number; grade?: string; findings_count?: number }>("/api/scan/public", { method: "POST", body: JSON.stringify(body) }),
  get: (scanId: string, token: string) =>
    request<Scan>("/api/scan/" + scanId, { token }),
  list: (token: string) =>
    request<{ scans: ScanListItem[] }>("/api/scans", { token }),
  rescan: (scanId: string, token: string) =>
    request<{ scan_id: string; domain: string; status: string; score?: number; grade?: string }>("/api/scan/" + scanId + "/rescan", { method: "POST", token }),
};

// Findings
export const findingsApi = {
  list: (scanId: string, token: string) =>
    request<{ findings: Finding[]; scan_id: string; score?: number; grade?: string }>("/api/findings/" + scanId, { token }),
  ignore: (findingId: string, body: { reason?: string; scan_id?: string }, token: string) =>
    request<{ message: string }>("/api/findings/" + findingId + "/ignore", { method: "POST", body: JSON.stringify(body), token }),
  fix: (findingId: string, token: string) =>
    request<{ message: string; scan_id: string }>("/api/findings/" + findingId + "/fix", { method: "POST", token }),
};

// Domains
export const domainsApi = {
  list: (token: string) => request<{ domains: Domain[] }>("/api/domains", { token }),
  create: (body: { domain: string; label?: string; scan_frequency?: string; notify_email?: string; notify_slack?: string }, token: string) =>
    request<Domain>("/api/domains", { method: "POST", body: JSON.stringify(body), token }),
  update: (domainId: string, body: { label?: string; scan_frequency?: string; notify_email?: string; notify_slack?: string }, token: string) =>
    request<Domain>("/api/domains/" + domainId, { method: "PUT", body: JSON.stringify(body), token }),
  delete: (domainId: string, token: string) =>
    request<{ message: string }>("/api/domains/" + domainId, { method: "DELETE", token }),
};

// Reports
export const reportsApi = {
  list: (token: string) => request<{ reports: ReportListItem[] }>("/api/reports", { token }),
  generate: (body: { scan_id: string; sections?: string[] }, token: string) =>
    request<ReportListItem>("/api/reports/generate", { method: "POST", body: JSON.stringify(body), token }),
  pdfUrl: (reportId: string) => `${API_URL}/api/reports/${reportId}/pdf`,
};

// Billing
export const billingApi = {
  checkout: (body: { plan: string }, token: string) =>
    request<{ url: string }>("/api/billing/checkout", { method: "POST", body: JSON.stringify(body), token }),
  portal: (token: string) =>
    request<{ url: string }>("/api/billing/portal", { method: "POST", token }),
  invoices: (token: string) =>
    request<{ invoices: { id: string; amount_due: number; status: string; pdf_url?: string; created: number }[] }>("/api/billing/invoices", { token }),
};

// Ask HAWK
export const hawkApi = {
  chat: (body: { message: string; scan_id?: string; conversation_history?: { role: string; content: string }[] }, token: string) =>
    request<{ reply: string; trigger_rescan?: string }>("/api/hawk/chat", { method: "POST", body: JSON.stringify(body), token }),
};

// Breach Check
export const breachApi = {
  check: (body: { domain: string; emails: string[] }, token: string) =>
    request<BreachCheckResponse>("/api/breach-check", { method: "POST", body: JSON.stringify(body), token }),
};

// Notifications
export const notificationsApi = {
  list: (token: string) =>
    request<{ notifications: Notification[] }>("/api/notifications", { token }),
  readAll: (token: string) =>
    request<{ message: string }>("/api/notifications/read-all", { method: "POST", token }),
};

// Types
export interface User {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  company: string | null;
  industry: string | null;
  province: string | null;
  plan: string;
  trial_ends_at: string | null;
  created_at: string;
}

export interface Scan {
  id: string;
  domain_id: string | null;
  user_id: string;
  triggered_by: string | null;
  status: string;
  score: number | null;
  grade: string | null;
  findings_json: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ScanListItem {
  id: string;
  domain_id: string | null;
  user_id: string;
  status: string;
  score: number | null;
  grade: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface Finding {
  id: string;
  severity: string;
  category: string;
  title: string;
  description: string;
  technical_detail: string;
  affected_asset: string;
  remediation: string;
  compliance: string[];
  ignored?: boolean;
  ignore_reason?: string | null;
}

export interface Domain {
  id: string;
  user_id: string;
  domain: string;
  label: string | null;
  scan_frequency: string | null;
  notify_email: string | null;
  notify_slack: string | null;
  created_at: string | null;
}

export interface ReportListItem {
  id: string;
  scan_id: string;
  domain: string;
  pdf_path: string | null;
  created_at: string | null;
}

export interface BreachEntry {
  name: string;
  title: string;
  breach_date: string;
  data_classes: string[];
  is_verified: boolean;
  pwn_count: number;
}

export interface EmailBreachResult {
  email: string;
  breached: boolean;
  breach_count: number;
  breaches: BreachEntry[];
  error?: string | null;
}

export interface BreachCheckResponse {
  domain: string;
  total_checked: number;
  breached_count: number;
  clean_count: number;
  results: EmailBreachResult[];
}

export interface Notification {
  id: string;
  user_id: string;
  type: string | null;
  title: string;
  body: string | null;
  read: boolean;
  created_at: string | null;
}
