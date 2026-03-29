/**
 * HAWK CRM API layer.
 *
 * Architecture:
 *   - Simple CRUD  → Supabase JS client (RLS enforced automatically)
 *   - Complex ops  → FastAPI on Ghost server (scans, commission calc, webhooks, reports, invites)
 *
 * This split means reps see only their own data via Supabase RLS,
 * while FastAPI handles business logic that requires server-side trust.
 */

import { getSupabaseClient } from "@/lib/supabase";
import type {
  Prospect,
  Client,
  ClientPlan,
  Commission,
  RepTask,
  ScanResult,
  CharlotteStats,
  SendingDomain,
  SequencePerformance,
  Ticket,
  PipelineStage,
  LostReasonData,
  CloseWonData,
  ApiResponse,
  CRMUser,
  Activity,
  EmailEvent,
  PipelineReport,
  CommissionReport,
  RepPerformance,
} from "@/types/crm";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "https://api.hawk.akbstudios.com";

// ─── FastAPI helper (complex ops only) ────────────────────────────────────────

async function apiCall<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const supabase = getSupabaseClient();
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string>),
  };

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) {
      const errText = await res.text().catch(() => "Unknown error");
      return { success: false, data: null, error: errText };
    }
    const json = await res.json();
    return { success: true, data: json as T, error: null };
  } catch (err) {
    return {
      success: false,
      data: null,
      error: err instanceof Error ? err.message : "Request failed",
    };
  }
}

// ─── Supabase helper ──────────────────────────────────────────────────────────

function sb() {
  return getSupabaseClient();
}

function toResponse<T>(data: T | null, error: { message: string } | null): ApiResponse<T> {
  if (error) return { success: false, data: null, error: error.message };
  return { success: true, data, error: null };
}

type ClientsJoinRow = {
  id: string;
  close_date: string;
  clawback_deadline: string | null;
  mrr: number;
  plan: ClientPlan;
  prospect_id: string | null;
  prospects?: { company_name?: string | null; domain?: string | null } | null;
};

/** Map Supabase `clients(...)` embed on commission rows into `Commission.client`. */
function mapCommissionsWithClientJoin(data: unknown[] | null): Commission[] {
  if (!data?.length) return (data ?? []) as Commission[];
  return data.map((row) => {
    const r = row as Record<string, unknown> & { clients?: ClientsJoinRow | ClientsJoinRow[] | null };
    const raw = r.clients;
    const j = Array.isArray(raw) ? raw[0] : raw;
    const { clients: _drop, ...rest } = r;
    if (!j || typeof j !== "object") {
      return rest as unknown as Commission;
    }
    const pr = j.prospects;
    const prospect: Prospect | undefined =
      pr && typeof pr === "object"
        ? {
            id: j.prospect_id ?? "",
            domain: pr.domain ?? "",
            company_name: pr.company_name ?? "",
            industry: null,
            city: null,
            province: null,
            stage: "closed_won",
            assigned_rep_id: null,
            hawk_score: null,
            source: "manual",
            consent_basis: null,
            is_hot: false,
            duplicate_of: null,
            lost_reason: null,
            lost_notes: null,
            reactivate_at: null,
            apollo_data: null,
            created_at: "",
            last_activity_at: "",
          }
        : undefined;
    const client = {
      id: j.id,
      prospect_id: j.prospect_id,
      plan: j.plan,
      mrr: Number(j.mrr),
      stripe_customer_id: null,
      stripe_subscription_id: null,
      closing_rep_id: null,
      csm_rep_id: null,
      status: "active" as const,
      close_date: j.close_date,
      clawback_deadline: j.clawback_deadline,
      churn_risk_score: "low" as const,
      nps_latest: null,
      last_login_at: null,
      created_at: "",
      prospect,
    } satisfies Client;
    return { ...(rest as object), client } as Commission;
  });
}

// ─── Prospects API ────────────────────────────────────────────────────────────

export const prospectsApi = {
  list: async (params?: {
    stage?: PipelineStage;
    source?: string;
    rep_id?: string;
    search?: string;
    is_hot?: boolean;
  }): Promise<ApiResponse<Prospect[]>> => {
    let query = sb()
      .from("prospects")
      .select("*, assigned_rep:assigned_rep_id(id, name, email, role)")
      .order("last_activity_at", { ascending: false });

    if (params?.stage) query = query.eq("stage", params.stage);
    if (params?.source) query = query.eq("source", params.source);
    if (params?.rep_id) query = query.eq("assigned_rep_id", params.rep_id);
    if (params?.is_hot) query = query.eq("is_hot", true);
    if (params?.search) {
      query = query.or(
        `company_name.ilike.%${params.search}%,domain.ilike.%${params.search}%`
      );
    }

    const { data, error } = await query;
    return toResponse(data as Prospect[] | null, error);
  },

  get: async (
    id: string
  ): Promise<ApiResponse<Prospect & { activities: Activity[]; scans: ScanResult[]; email_events: EmailEvent[] }>> => {
    const [prospectRes, activitiesRes, scansRes, emailsRes] = await Promise.all([
      sb()
        .from("prospects")
        .select("*")
        .eq("id", id)
        .single(),
      sb()
        .from("activities")
        .select("*")
        .eq("prospect_id", id)
        .order("created_at", { ascending: false }),
      sb()
        .from("crm_scans")
        .select("*")
        .eq("prospect_id", id)
        .order("created_at", { ascending: false }),
      sb()
        .from("email_events")
        .select("*")
        .eq("prospect_id", id)
        .order("sent_at", { ascending: false }),
    ]);

    if (prospectRes.error)
      return { success: false, data: null, error: prospectRes.error.message };

    return {
      success: true,
      data: {
        ...(prospectRes.data as Prospect),
        activities: (activitiesRes.data as Activity[]) ?? [],
        scans: (scansRes.data as ScanResult[]) ?? [],
        email_events: (emailsRes.data as EmailEvent[]) ?? [],
      },
      error: null,
    };
  },

  create: async (data: {
    domain: string;
    company_name: string;
    industry?: string;
    city?: string;
    province?: string;
    assigned_rep_id?: string;
  }): Promise<ApiResponse<Prospect>> => {
    // Suppression check
    const suppressed = await sb()
      .from("suppressions")
      .select("id")
      .or(`domain.eq.${data.domain},email.ilike.%@${data.domain}%`)
      .limit(1);
    if (suppressed.data && suppressed.data.length > 0) {
      return {
        success: false,
        data: null,
        error: `Domain ${data.domain} is on the suppression list and cannot be contacted.`,
      };
    }

    const { data: result, error } = await sb()
      .from("prospects")
      .insert({ ...data, stage: "new", source: data.assigned_rep_id ? "manual" : "charlotte" })
      .select()
      .single();
    return toResponse(result as Prospect | null, error);
  },

  update: async (id: string, updates: Partial<Prospect>): Promise<ApiResponse<Prospect>> => {
    const { data, error } = await sb()
      .from("prospects")
      .update({ ...updates, last_activity_at: new Date().toISOString() })
      .eq("id", id)
      .select()
      .single();
    return toResponse(data as Prospect | null, error);
  },

  move: async (id: string, stage: PipelineStage): Promise<ApiResponse<Prospect>> => {
    const { data, error } = await sb()
      .from("prospects")
      .update({ stage, last_activity_at: new Date().toISOString() })
      .eq("id", id)
      .select()
      .single();

    if (!error && data) {
      await sb().from("activities").insert({
        prospect_id: id,
        type: "stage_changed",
        metadata: { to_stage: stage },
      });
    }
    return toResponse(data as Prospect | null, error);
  },

  reassign: async (id: string, assigned_rep_id: string): Promise<ApiResponse<Prospect>> => {
    const supabase = getSupabaseClient();
    const {
      data: { user: authUser },
    } = await supabase.auth.getUser();

    const { data, error } = await sb()
      .from("prospects")
      .update({ assigned_rep_id, last_activity_at: new Date().toISOString() })
      .eq("id", id)
      .select("*, assigned_rep:assigned_rep_id(id, name, email, role)")
      .single();

    if (!error && data) {
      await sb().from("activities").insert({
        prospect_id: id,
        type: "reassigned",
        created_by: authUser?.id ?? null,
        metadata: { assigned_rep_id },
      });
    }
    return toResponse(data as Prospect | null, error);
  },

  moveLost: async (id: string, lostData: LostReasonData): Promise<ApiResponse<Prospect>> => {
    const { data, error } = await sb()
      .from("prospects")
      .update({
        stage: "lost",
        lost_reason: lostData.reason,
        lost_notes: lostData.notes,
        reactivate_at: lostData.reactivate_at,
        last_activity_at: new Date().toISOString(),
      })
      .eq("id", id)
      .select()
      .single();

    if (!error) {
      await sb().from("activities").insert({
        prospect_id: id,
        type: "stage_changed",
        metadata: { to_stage: "lost", reason: lostData.reason },
      });
    }
    return toResponse(data as Prospect | null, error);
  },

  /** Close Won — complex operation goes through FastAPI (creates client + commissions) */
  closeWon: (id: string, data: CloseWonData) =>
    apiCall<Client>(`/api/crm/prospects/${id}/close`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** Run HAWK scan — goes through FastAPI (calls Scanner service) */
  runScan: (id: string) =>
    apiCall<ScanResult>(`/api/crm/prospects/${id}/scan`, { method: "POST" }),

  logCall: async (
    id: string,
    data: {
      duration_minutes: number;
      outcome: "answered" | "voicemail" | "no_answer";
      notes?: string;
      next_action?: string;
    }
  ): Promise<ApiResponse<Activity>> => {
    const { data: result, error } = await sb()
      .from("activities")
      .insert({
        prospect_id: id,
        type: "call",
        notes: data.notes,
        metadata: {
          duration_minutes: data.duration_minutes,
          outcome: data.outcome,
          next_action: data.next_action,
        },
      })
      .select("*")
      .single();

    if (!error) {
      await sb()
        .from("prospects")
        .update({ last_activity_at: new Date().toISOString() })
        .eq("id", id);
    }
    return toResponse(result as Activity | null, error);
  },

  addNote: async (id: string, notes: string): Promise<ApiResponse<Activity>> => {
    const { data, error } = await sb()
      .from("activities")
      .insert({
        prospect_id: id,
        type: "note_added",
        notes,
      })
      .select("*")
      .single();

    if (!error) {
      await sb()
        .from("prospects")
        .update({ last_activity_at: new Date().toISOString() })
        .eq("id", id);
    }
    return toResponse(data as Activity | null, error);
  },

  markHot: async (id: string, is_hot: boolean): Promise<ApiResponse<Prospect>> => {
    const { data, error } = await sb()
      .from("prospects")
      .update({ is_hot, last_activity_at: new Date().toISOString() })
      .eq("id", id)
      .select()
      .single();

    if (!error && is_hot) {
      await sb().from("activities").insert({
        prospect_id: id,
        type: "hot_flagged",
        metadata: { is_hot },
      });
    }
    return toResponse(data as Prospect | null, error);
  },
};

// ─── Clients API ──────────────────────────────────────────────────────────────

export const clientsApi = {
  list: async (params?: {
    status?: string;
    churn_risk?: string;
    rep_id?: string;
  }): Promise<ApiResponse<Client[]>> => {
    let query = sb()
      .from("clients")
      .select("*, prospect:prospect_id(id, company_name, domain), closing_rep:closing_rep_id(id, name, email)")
      .order("close_date", { ascending: false });

    if (params?.status) query = query.eq("status", params.status);
    if (params?.churn_risk) query = query.eq("churn_risk_score", params.churn_risk);
    if (params?.rep_id) query = query.eq("closing_rep_id", params.rep_id);

    const { data, error } = await query;
    return toResponse(data as Client[] | null, error);
  },

  get: async (
    id: string
  ): Promise<ApiResponse<Client & { activities: Activity[]; scans: ScanResult[] }>> => {
    const [clientRes, activitiesRes, scansRes] = await Promise.all([
      sb()
        .from("clients")
        .select("*")
        .eq("id", id)
        .single(),
      sb()
        .from("activities")
        .select("*")
        .eq("client_id", id)
        .order("created_at", { ascending: false }),
      sb()
        .from("crm_scans")
        .select("*")
        .eq("client_id", id)
        .order("created_at", { ascending: false }),
    ]);

    if (clientRes.error)
      return { success: false, data: null, error: clientRes.error.message };

    return {
      success: true,
      data: {
        ...(clientRes.data as Client),
        activities: (activitiesRes.data as Activity[]) ?? [],
        scans: (scansRes.data as ScanResult[]) ?? [],
      },
      error: null,
    };
  },

  update: async (id: string, updates: Partial<Client>): Promise<ApiResponse<Client>> => {
    const { data, error } = await sb()
      .from("clients")
      .update(updates)
      .eq("id", id)
      .select()
      .single();
    return toResponse(data as Client | null, error);
  },

  logNPS: async (id: string, score: number): Promise<ApiResponse<Client>> => {
    const { data, error } = await sb()
      .from("clients")
      .update({ nps_latest: score })
      .eq("id", id)
      .select()
      .single();

    if (!error) {
      await sb().from("activities").insert({
        client_id: id,
        type: "note_added",
        notes: `NPS score logged: ${score}/10`,
        metadata: { nps_score: score },
      });
    }
    return toResponse(data as Client | null, error);
  },

  /** Generate + send PDF report — goes through FastAPI */
  generateReport: (id: string) =>
    apiCall<{ report_url: string }>(`/api/crm/clients/${id}/report`, {
      method: "POST",
    }),
};

// ─── Commissions API ──────────────────────────────────────────────────────────

export const commissionsApi = {
  /**
   * Rep's commissions (RLS). Optionally filter by month; pass `limit` for history charts
   * without loading the full table. Joins `clients` for clawback / company context.
   */
  myEarnings: async (
    monthYear?: string,
    opts?: { limit?: number }
  ): Promise<ApiResponse<Commission[]>> => {
    let query = sb()
      .from("commissions")
      .select(
        `
        *,
        clients (
          id,
          close_date,
          clawback_deadline,
          mrr,
          plan,
          prospect_id,
          prospects ( company_name, domain )
        )
      `
      )
      .order("calculated_at", { ascending: false });

    if (monthYear) query = query.eq("month_year", monthYear);
    if (opts?.limit != null) query = query.limit(opts.limit);

    const { data, error } = await query;
    return toResponse(mapCommissionsWithClientJoin(data as unknown[] | null), error);
  },

  list: async (repId?: string, monthYear?: string): Promise<ApiResponse<Commission[]>> => {
    let query = sb()
      .from("commissions")
      .select("*")
      .order("calculated_at", { ascending: false });

    if (repId) query = query.eq("rep_id", repId);
    if (monthYear) query = query.eq("month_year", monthYear);

    const { data, error } = await query;
    return toResponse(data as Commission[] | null, error);
  },

  /** Trigger month-end recalculation — FastAPI business logic */
  calculate: (monthYear: string) =>
    apiCall<{ calculated: number }>("/api/crm/commissions/calculate", {
      method: "POST",
      body: JSON.stringify({ month_year: monthYear }),
    }),

  /** Deel export CSV — FastAPI */
  exportCSV: (monthYear: string) =>
    apiCall<{ url: string }>(`/api/crm/commissions/export?month_year=${monthYear}`),
};

// ─── Rep tasks (Supabase `rep_tasks`) ─────────────────────────────────────────

export const repTasksApi = {
  list: async (params?: {
    openOnly?: boolean;
    limit?: number;
  }): Promise<ApiResponse<RepTask[]>> => {
    let query = sb()
      .from("rep_tasks")
      .select("*, prospect:prospect_id ( id, company_name, domain )")
      .order("due_at", { ascending: true });

    if (params?.openOnly !== false) query = query.is("completed_at", null);
    if (params?.limit != null) query = query.limit(params.limit);

    const { data, error } = await query;
    return toResponse(data as RepTask[] | null, error);
  },

  create: async (payload: {
    title: string;
    due_at: string;
    prospect_id?: string | null;
    notes?: string | null;
  }): Promise<ApiResponse<RepTask>> => {
    const supabase = getSupabaseClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      return { success: false, data: null, error: "Not authenticated" };
    }

    const { data, error } = await sb()
      .from("rep_tasks")
      .insert({
        rep_id: user.id,
        title: payload.title,
        due_at: payload.due_at,
        prospect_id: payload.prospect_id ?? null,
        notes: payload.notes ?? null,
      })
      .select("*, prospect:prospect_id ( id, company_name, domain )")
      .single();

    if (!error && data?.prospect_id) {
      await sb().from("activities").insert({
        prospect_id: data.prospect_id,
        type: "task_created",
        created_by: user.id,
        metadata: { rep_task_id: data.id, title: payload.title },
      });
    }

    return toResponse(data as RepTask | null, error);
  },

  complete: async (id: string): Promise<ApiResponse<RepTask>> => {
    const { data: existing, error: fetchErr } = await sb()
      .from("rep_tasks")
      .select("prospect_id")
      .eq("id", id)
      .single();
    if (fetchErr) {
      return { success: false, data: null, error: fetchErr.message };
    }

    const { data, error } = await sb()
      .from("rep_tasks")
      .update({ completed_at: new Date().toISOString() })
      .eq("id", id)
      .select()
      .single();

    if (!error && existing?.prospect_id) {
      await sb().from("activities").insert({
        prospect_id: existing.prospect_id,
        type: "task_completed",
        metadata: { rep_task_id: id },
      });
    }

    return toResponse(data as RepTask | null, error);
  },
};

// ─── Scans API ────────────────────────────────────────────────────────────────

export const scansApi = {
  getForProspect: async (prospectId: string): Promise<ApiResponse<ScanResult[]>> => {
    const { data, error } = await sb()
      .from("crm_scans")
      .select("*")
      .eq("prospect_id", prospectId)
      .order("created_at", { ascending: false });
    return toResponse(data as ScanResult[] | null, error);
  },

  getForClient: async (clientId: string): Promise<ApiResponse<ScanResult[]>> => {
    const { data, error } = await sb()
      .from("crm_scans")
      .select("*")
      .eq("client_id", clientId)
      .order("created_at", { ascending: false });
    return toResponse(data as ScanResult[] | null, error);
  },
};

// ─── Charlotte API — FastAPI (integrations, assignment logic) ─────────────────

export const charlotteApi = {
  stats: () => apiCall<CharlotteStats>("/api/crm/charlotte/stats"),
  domains: () => apiCall<SendingDomain[]>("/api/crm/charlotte/domains"),
  sequences: () => apiCall<SequencePerformance[]>("/api/crm/charlotte/sequences"),

  assign: (prospectId: string, repId: string) =>
    apiCall<Prospect>("/api/crm/charlotte/assign", {
      method: "POST",
      body: JSON.stringify({ prospect_id: prospectId, rep_id: repId }),
    }),

  updateAssignmentRules: (rules: Record<string, unknown>) =>
    apiCall<{ success: boolean }>("/api/crm/charlotte/assignment-rules", {
      method: "PUT",
      body: JSON.stringify(rules),
    }),
};

// ─── Tickets API ──────────────────────────────────────────────────────────────

export const ticketsApi = {
  submit: async (data: {
    raw_text: string;
    what_were_you_doing?: string;
    screenshot_url?: string;
  }): Promise<ApiResponse<Ticket>> => {
    const combined = data.what_were_you_doing
      ? `${data.raw_text}\n\nWhat I was trying to do: ${data.what_were_you_doing}`
      : data.raw_text;

    const supabase = getSupabaseClient();
    const {
      data: { user: authUser },
    } = await supabase.auth.getUser();
    if (!authUser) {
      return { success: false, data: null, error: "Not authenticated" };
    }

    const { data: result, error } = await sb()
      .from("tickets")
      .insert({
        raw_text: combined,
        channel: "in_crm",
        status: "received",
        submitted_by: authUser.id,
      })
      .select()
      .single();
    return toResponse(result as Ticket | null, error);
  },

  list: async (params?: {
    status?: string;
    channel?: string;
    submitted_by?: string;
  }): Promise<ApiResponse<Ticket[]>> => {
    let query = sb()
      .from("tickets")
      .select("*")
      .order("created_at", { ascending: false });

    if (params?.status) query = query.eq("status", params.status);
    if (params?.channel) query = query.eq("channel", params.channel);
    if (params?.submitted_by) query = query.eq("submitted_by", params.submitted_by);

    const { data, error } = await query;
    return toResponse(data as Ticket[] | null, error);
  },

  updateStatus: async (id: string, status: string, resolution_type?: string): Promise<ApiResponse<Ticket>> => {
    const { data, error } = await sb()
      .from("tickets")
      .update({
        status,
        resolution_type,
        resolved_at: ["resolved", "duplicate", "monitoring"].includes(status)
          ? new Date().toISOString()
          : null,
      })
      .eq("id", id)
      .select()
      .single();
    return toResponse(data as Ticket | null, error);
  },

  stats: () => apiCall<{
    avg_resolution_hours: number;
    auto_resolve_pct: number;
    user_error_pct: number;
    open_over_4h: number;
  }>("/api/crm/tickets/stats"),
};

// ─── Reports API — FastAPI (aggregations) ─────────────────────────────────────

export const reportsApi = {
  pipeline: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    return apiCall<PipelineReport>(`/api/crm/reports/pipeline${qs}`);
  },
  commission: (monthYear: string) =>
    apiCall<CommissionReport>(`/api/crm/reports/commission?month_year=${monthYear}`),
  charlotte: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    return apiCall<Record<string, unknown>>(`/api/crm/reports/charlotte${qs}`);
  },
  clientHealth: () =>
    apiCall<Record<string, unknown>>("/api/crm/reports/client-health"),
  repPerformance: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    return apiCall<RepPerformance[]>(`/api/crm/reports/rep-performance${qs}`);
  },
  forecast: (monthsAhead?: number) =>
    apiCall<Record<string, unknown>>(
      `/api/crm/reports/forecast${monthsAhead != null ? `?months_ahead=${monthsAhead}` : ""}`
    ),
  attribution: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    return apiCall<Record<string, unknown>>(`/api/crm/reports/attribution${qs}`);
  },
};

// ─── Users API ────────────────────────────────────────────────────────────────

export const usersApi = {
  me: async (): Promise<ApiResponse<CRMUser>> => {
    const supabase = getSupabaseClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, data: null, error: "Not authenticated" };

    const { data, error } = await sb()
      .from("users")
      .select("*, team_lead:team_lead_id(id, name, email, role)")
      .eq("id", user.id)
      .single();
    return toResponse(data as CRMUser | null, error);
  },

  list: async (): Promise<ApiResponse<CRMUser[]>> => {
    const { data, error } = await sb()
      .from("users")
      .select("*, team_lead:team_lead_id(id, name, email, role)")
      .order("created_at", { ascending: false });
    return toResponse(data as CRMUser[] | null, error);
  },

  /** Invite — FastAPI (sends email via Charlotte) */
  invite: (data: { name: string; email: string; role: string; team_lead_id?: string }) =>
    apiCall<CRMUser>("/api/crm/users/invite", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: async (id: string, updates: Partial<CRMUser>): Promise<ApiResponse<CRMUser>> => {
    const { data, error } = await sb()
      .from("users")
      .update(updates)
      .eq("id", id)
      .select()
      .single();
    return toResponse(data as CRMUser | null, error);
  },

  /** At-risk status actions — FastAPI (complex: notifications, audit log) */
  updateStatus: (
    id: string,
    status: "active" | "at_risk" | "inactive",
    action?: "extend_7d" | "begin_removal" | "on_leave"
  ) =>
    apiCall<CRMUser>(`/api/crm/users/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({ status, action }),
    }),

  performance: (id: string, params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    return apiCall<RepPerformance>(`/api/crm/users/${id}/performance${qs}`);
  },
};

// ─── Apollo enrichment — FastAPI ──────────────────────────────────────────────

export const apolloApi = {
  enrich: (domain: string) =>
    apiCall<Record<string, unknown>>("/api/crm/apollo/enrich", {
      method: "POST",
      body: JSON.stringify({ domain }),
    }),
};

// ─── Audit log ────────────────────────────────────────────────────────────────

export const auditApi = {
  list: async (params?: {
    user_id?: string;
    record_type?: string;
    from?: string;
    to?: string;
    limit?: number;
    offset?: number;
  }): Promise<ApiResponse<Record<string, unknown>[]>> => {
    let query = sb()
      .from("audit_log")
      .select("*, user:user_id(id, name, email, role)")
      .order("created_at", { ascending: false })
      .limit(params?.limit ?? 100)
      .range(params?.offset ?? 0, (params?.offset ?? 0) + (params?.limit ?? 100) - 1);

    if (params?.user_id) query = query.eq("user_id", params.user_id);
    if (params?.record_type) query = query.eq("record_type", params.record_type);
    if (params?.from) query = query.gte("created_at", params.from);
    if (params?.to) query = query.lte("created_at", params.to);

    const { data, error } = await query;
    return toResponse(data as Record<string, unknown>[] | null, error);
  },
};

// ─── Suppressions ─────────────────────────────────────────────────────────────

export const suppressionsApi = {
  list: async (): Promise<ApiResponse<Record<string, unknown>[]>> => {
    const { data, error } = await sb()
      .from("suppressions")
      .select("*")
      .order("added_at", { ascending: false });
    return toResponse(data as Record<string, unknown>[] | null, error);
  },

  add: async (params: {
    domain?: string;
    email?: string;
    reason: "unsubscribe" | "bounce" | "manual";
  }): Promise<ApiResponse<Record<string, unknown>>> => {
    const { data, error } = await sb()
      .from("suppressions")
      .insert(params)
      .select()
      .single();
    return toResponse(data as Record<string, unknown> | null, error);
  },
};

// ─── Realtime helpers ─────────────────────────────────────────────────────────

/** Subscribe to live scoreboard changes (commissions table) */
export function subscribeToScoreboard(
  onUpdate: (payload: Record<string, unknown>) => void
) {
  return sb()
    .channel("crm-scoreboard")
    .on(
      "postgres_changes",
      { event: "*", schema: "public", table: "commissions" },
      (payload) => onUpdate(payload as Record<string, unknown>)
    )
    .subscribe();
}

/** Subscribe to live activity feed (activities table) */
export function subscribeToActivityFeed(
  onUpdate: (payload: Record<string, unknown>) => void
) {
  return sb()
    .channel("crm-activity-feed")
    .on(
      "postgres_changes",
      { event: "INSERT", schema: "public", table: "activities" },
      (payload) => onUpdate(payload as Record<string, unknown>)
    )
    .subscribe();
}
