/**
 * HAWK API client. All requests use JSON and optional Bearer token.
 * Set NEXT_PUBLIC_API_URL to your FastAPI base (e.g. Railway); defaults to http://localhost:8000.
 */

/** Backend API (Railway, etc.) — not the same as NEXT_PUBLIC_SITE_URL unless you proxy /api. */
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Guarantee endpoints: in the browser use same-origin `/api/guarantee/*` (Next.js proxies to FastAPI). Supabase only sends Auth emails; codes are sent by the API. */
function guaranteeApiUrl(): string {
  if (typeof window !== "undefined") return "";
  return API_URL;
}

export type ApiError = { detail: string | { msg: string }[] };

/**
 * Error thrown by {@link request} on non-2xx responses. The HTTP status code
 * is attached as `.status` so callers can branch on it without string-matching
 * the server's human-readable detail (which varies per endpoint and may be
 * localised in the future).
 */
export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

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
    throw new HttpError(res.status, detail);
  }
  return data as T;
}

/** Portal self-serve (`/api/portal/bootstrap`, primary-domain): browser uses same-origin Next proxies; server/SSR uses FastAPI base. */
async function portalRequest<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, ...init } = options;
  const base = typeof window !== "undefined" ? "" : API_URL;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${base}${path}`, { ...init, headers });
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ")
          : data.detail?.[0]?.msg || data.error || "Request failed";
    throw new Error(detail);
  }
  return data as T;
}

async function guaranteeRequest<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, ...init } = options;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const base = guaranteeApiUrl();
  const res = await fetch(`${base}${path}`, { ...init, headers });
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
  /** Public scan (no auth). Default backend depth is `full`; pass `fast` for a lighter / quicker pass. */
  startPublic: (body: { domain: string; scan_depth?: "fast" | "full" }) =>
    request<PublicScanResult>("/api/scan/public", { method: "POST", body: JSON.stringify(body) }),
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
  /**
   * Hosted Stripe Checkout (optional). Marketing uses embedded /checkout + create-payment-intent instead.
   */
  checkoutPublic: (body: { hawk_product: "starter" | "shield" }) => {
    return request<{ url: string; mode?: string; product?: string }>("/api/billing/checkout-public", { method: "POST", body: JSON.stringify(body) });
  },
  /**
   * Hosted: pass session id string. Embedded: pass { subscription_id, email, name } after card confirmation.
   */
  completeCheckoutSession: (
    bodyOrSessionId:
      | string
      | { session_id?: string; subscription_id?: string; email?: string; name?: string },
  ) => {
    const body =
      typeof bodyOrSessionId === "string" ? { session_id: bodyOrSessionId } : bodyOrSessionId;
    return request<{ redirect_url: string }>("/api/billing/checkout-complete", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  /** Embedded Elements — incomplete subscription + client_secret for confirmCardPayment. */
  createPaymentIntent: (body: {
    email: string;
    name: string;
    hawk_product: "starter" | "shield";
    test_mode: boolean;
  }) =>
    request<{ client_secret: string; subscription_id: string; customer_id: string }>(
      "/api/billing/create-payment-intent",
      { method: "POST", body: JSON.stringify(body) },
    ),
  /** Same as createPaymentIntent; email is taken from Supabase JWT (signed-in portal user). */
  createPaymentIntentPortal: (
    body: { name?: string; hawk_product: "starter" | "shield"; test_mode: boolean },
    token: string,
  ) =>
    request<{ client_secret: string; subscription_id: string; customer_id: string }>(
      "/api/billing/create-payment-intent-portal",
      { method: "POST", body: JSON.stringify(body), token },
    ),
  checkout: (body: { plan: string }, token: string) =>
    request<{ url: string }>("/api/billing/checkout", { method: "POST", body: JSON.stringify(body), token }),
  portal: (token: string) =>
    request<{ url: string }>("/api/billing/portal", { method: "POST", token }),
  invoices: (token: string) =>
    request<{ invoices: { id: string; amount_due: number; status: string; pdf_url?: string; created: number }[] }>("/api/billing/invoices", { token }),
};

/** Account-first portal: bootstrap CRM rows after magic-link sign-in. */
export const portalApi = {
  bootstrap: (token: string) =>
    portalRequest<{ ok: boolean; client_id: string; created: boolean }>("/api/portal/bootstrap", {
      method: "POST",
      token,
    }),
  setPrimaryDomain: (body: { domain: string }, token: string) =>
    portalRequest<{ ok: string; domain: string }>("/api/portal/primary-domain", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
  /**
   * Stamp clients.last_portal_login_at so PortalGate stops redirecting
   * subsequent visits to /portal/welcome (priority list #32). Fire-and-forget
   * from the welcome page mount — we don't want UI to hang on a slow Supabase
   * round-trip.
   */
  markFirstLoginSeen: (token: string) =>
    portalRequest<{ ok: string; last_portal_login_at: string }>(
      "/api/portal/mark-first-login-seen",
      { method: "POST", token },
    ),
  /**
   * One-click incident report (priority list #34). Logs the incident,
   * starts an SLA clock, SMSes the CEO, emails the client a confirmation,
   * and mirrors the event into the internal support-ticket queue. Returns
   * the new case id + SLA deadline so the UI can show an acknowledgment.
   */
  reportIncident: (body: { description?: string }, token: string) =>
    portalRequest<{
      ok: boolean;
      incident_id: string;
      case_id: string;
      reported_at: string;
      sla_deadline: string;
      sla_minutes: number;
      ceo_sms_status: string;
      client_email_status: string;
      support_ticket_id: string | null;
    }>("/api/portal/incident-report", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
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

/** Gated Breach Response Guarantee document (email code + JWT). */
export const guaranteeApi = {
  requestCode: (body: { email: string; name: string; company: string }) =>
    guaranteeRequest<{ ok: string }>("/api/guarantee/request-code", { method: "POST", body: JSON.stringify(body) }),
  verify: (body: { email: string; code: string }) =>
    guaranteeRequest<{ access_token: string; token_type: string }>("/api/guarantee/verify", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getDocument: (accessToken: string) =>
    guaranteeRequest<{ markdown: string }>("/api/guarantee/document", { token: accessToken }),
};

/** Homepage lead — always treat as success in UI; errors logged only. */
export const marketingApi = {
  homepageLead: async (body: {
    email: string;
    domain: string;
    hawk_score?: number | null;
    grade?: string | null;
    top_finding?: string | null;
    findings_plain?: string[];
  }) => {
    try {
      return await request<{ ok: string }>("/api/marketing/homepage-lead", {
        method: "POST",
        body: JSON.stringify(body),
      });
    } catch (e) {
      console.error("marketing homepage-lead", e);
      return { ok: "true" };
    }
  },
  /**
   * `/free-scan` landing page — US business owner enters domain + email,
   * receives a 3-finding report within 24 hours. Returns `{ok: true}` on
   * success. Throws on 400 (invalid domain / email) so the form can show
   * an inline error, and on 429 (rate-limit hit).
   */
  freeScan: async (body: {
    name?: string;
    email: string;
    domain: string;
    company_name?: string;
    vertical?: string;
  }) => {
    return await request<{ ok: boolean }>("/api/marketing/free-scan", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  /**
   * Pre-populated homepage scan result (priority list #45). Returns the
   * cached worst-of-N scan picked offline by `scripts/pick_worst_dental.py`
   * so visitors see findings the moment the page loads. Resolves to `null`
   * on 404 (cache not yet populated) so the widget falls back to its idle
   * "type your domain" state.
   */
  getHomepagePresetScan: async (): Promise<PublicScanResult | null> => {
    try {
      return await request<PublicScanResult>("/api/marketing/homepage-preset-scan");
    } catch (e) {
      if (e instanceof HttpError && e.status === 404) {
        return null;
      }
      console.error("marketing homepage-preset-scan", e);
      return null;
    }
  },
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

export interface PublicScanFindingPreview {
  text: string;
  severity: string;
  /** HIPAA 2026 Security Rule control tags, e.g. ["§164.312(d) — 2026 Security Rule"]. */
  hipaa_controls?: string[];
}

export interface PublicScanResult {
  domain: string;
  status: string;
  score?: number;
  grade?: string;
  findings_count?: number;
  issues_count?: number;
  findings_plain?: string[];
  /** Severity-coloured lines for homepage (preferred over findings_plain alone). */
  findings_preview?: PublicScanFindingPreview[];
  attack_paths_count?: number;
  top_attack_path?: string;
  breach_baseline_usd?: number;
  breach_cost_summary?: string;
  /** Scanner build id e.g. 2.1-fast (from hawk-scanner-v2) */
  scan_version?: string | null;
  /** Insurance readiness posture, 0–100. Falls back to HAWK score when absent. */
  insurance_readiness?: number;
  /** Ransomware threat intel blurb shown in the scan widget when present. */
  ransomware_intel?: string;
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
