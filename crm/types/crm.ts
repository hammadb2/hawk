// ─── Role & Stage Enums ────────────────────────────────────────────────────────

export type UserRole = "ceo" | "hos" | "team_lead" | "rep" | "csm";

export type PipelineStage =
  | "new"
  | "scanned"
  | "loom_sent"
  | "replied"
  | "call_booked"
  | "proposal_sent"
  | "closed_won"
  | "lost";

export type ActivityType =
  | "call"
  | "email_sent"
  | "stage_changed"
  | "scan_run"
  | "note_added"
  | "loom_sent"
  | "task_created"
  | "task_completed"
  | "hot_flagged"
  | "reassigned"
  | "close_won";

export type CommissionType =
  | "closing"
  | "residual"
  | "bonus"
  | "override"
  | "clawback";

export type CommissionStatus = "pending" | "paid" | "clawback";

export type ClientPlan = "starter" | "shield" | "enterprise" | "custom";

export type ClientStatus = "active" | "past_due" | "churned" | "paused";

export type ProspectSource = "charlotte" | "manual" | "inbound" | "inbound_signup" | "referral";

export type ChurnRisk = "low" | "medium" | "high" | "critical";

export type UserStatus = "active" | "at_risk" | "inactive";

export type TicketChannel = "in_crm" | "whatsapp" | "email" | "auto_detected";

export type TicketStatus =
  | "received"
  | "in_progress"
  | "resolved"
  | "duplicate"
  | "monitoring";

export type ReplySentiment = "positive" | "negative" | "question" | "ooo";

// ─── Core Entities ─────────────────────────────────────────────────────────────

export interface CRMUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  team_lead_id: string | null;
  status: UserStatus;
  last_close_at: string | null;
  whatsapp_number: string | null;
  invited_by: string | null;
  created_at: string;
  daily_call_target?: number | null;
  daily_loom_target?: number | null;
  daily_scan_target?: number | null;
  // Computed / joined
  team_lead?: CRMUser;
  avatar_url?: string;
}

export interface Prospect {
  id: string;
  domain: string;
  company_name: string;
  industry: string | null;
  city: string | null;
  province: string | null;
  stage: PipelineStage;
  assigned_rep_id: string | null;
  hawk_score: number | null;
  source: ProspectSource;
  consent_basis: string | null;
  is_hot: boolean;
  duplicate_of: string | null;
  lost_reason: string | null;
  lost_notes: string | null;
  reactivate_at: string | null;
  apollo_data: Record<string, unknown> | null;
  created_at: string;
  last_activity_at: string;
  // Computed / joined
  assigned_rep?: CRMUser;
}

export interface Client {
  id: string;
  prospect_id: string | null;
  plan: ClientPlan;
  mrr: number;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  closing_rep_id: string | null;
  csm_rep_id: string | null;
  status: ClientStatus;
  close_date: string;
  clawback_deadline: string | null;
  churn_risk_score: ChurnRisk;
  nps_latest: number | null;
  last_login_at: string | null;
  created_at: string;
  // Computed / joined
  prospect?: Prospect;
  closing_rep?: CRMUser;
  csm_rep?: CRMUser;
}

export interface Activity {
  id: string;
  prospect_id: string | null;
  client_id: string | null;
  type: ActivityType;
  created_by: string | null;
  notes: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  // Computed / joined
  author?: CRMUser;
}

export interface EmailEvent {
  id: string;
  prospect_id: string | null;
  smartlead_event_type: string;
  subject: string | null;
  sequence_step: number | null;
  sent_at: string | null;
  opened_at: string | null;
  open_count: number;
  clicked_at: string | null;
  click_count: number;
  replied_at: string | null;
  reply_sentiment: ReplySentiment | null;
  created_at: string;
}

export interface ScanResult {
  id: string;
  prospect_id: string | null;
  client_id: string | null;
  hawk_score: number | null;
  findings: ScanFinding[];
  triggered_by: string | null;
  status: "pending" | "complete" | "failed";
  created_at: string;
  // Computed
  triggered_by_user?: CRMUser;
}

export interface ScanFinding {
  id: string;
  title: string;
  description: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: string;
  remediation?: string;
}

export interface Commission {
  id: string;
  rep_id: string;
  type: CommissionType;
  amount: number;
  client_id: string | null;
  month_year: string; // format: "2026-03"
  status: CommissionStatus;
  deel_payment_ref: string | null;
  calculated_at: string;
  // Computed / joined
  rep?: CRMUser;
  client?: Client;
}

/** Rep follow-up tasks (`rep_tasks` table). */
export interface RepTask {
  id: string;
  rep_id: string;
  prospect_id: string | null;
  title: string;
  due_at: string;
  completed_at: string | null;
  notes: string | null;
  created_at: string;
  prospect?: Pick<Prospect, "id" | "company_name" | "domain">;
}

export interface Ticket {
  id: string;
  submitted_by: string | null;
  channel: TicketChannel;
  raw_text: string;
  classification: string | null;
  severity: number | null; // 1-5
  status: TicketStatus;
  triage_diagnosis: string | null;
  pr_url: string | null;
  resolved_at: string | null;
  resolution_type: string | null;
  parent_ticket_id: string | null;
  created_at: string;
  // Computed / joined
  submitter?: CRMUser;
}

export interface CharlotteStats {
  sent_today: number;
  opened_today: number;
  replied_today: number;
  positive_replies: number;
  prospects_created: number;
  closes_attributed: number;
  last_ping: string;
  status: "healthy" | "degraded" | "down";
}

export interface SendingDomain {
  id: string;
  domain: string;
  warmup_status: "warming" | "active" | "paused" | "flagged";
  daily_limit: number;
  bounce_rate: number;
  spam_rate: number;
  delivery_rate_7d: number;
}

export interface SequencePerformance {
  sequence_id: string;
  name: string;
  step: number;
  send_count: number;
  open_rate: number;
  click_rate: number;
  reply_rate: number;
}

// ─── Notification ──────────────────────────────────────────────────────────────

export interface Notification {
  id: string;
  user_id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  link?: string;
  created_at: string;
}

// ─── Report Types ──────────────────────────────────────────────────────────────

export interface PipelineReport {
  total_prospects: number;
  by_stage: Record<PipelineStage, number>;
  conversion_rates: Record<string, number>;
  avg_days_per_stage: Record<PipelineStage, number>;
  bottlenecks: PipelineStage[];
}

export interface CommissionReport {
  total_paid: number;
  total_pending: number;
  total_clawbacks: number;
  by_rep: Array<{
    rep: CRMUser;
    closing: number;
    residual: number;
    bonus: number;
    override: number;
    total: number;
  }>;
  month_year: string;
}

export interface RepPerformance {
  rep: CRMUser;
  closes_this_month: number;
  monthly_target: number;
  conversion_rate: number;
  avg_days_to_close: number;
  commission_earned: number;
  rank: number;
  pipeline_by_stage: Record<PipelineStage, number>;
  days_since_last_close: number;
  at_risk_14_day: boolean;
}

// ─── Data Bridge Types ─────────────────────────────────────────────────────────

export interface ClientHealthSync {
  id: string;
  client_id: string;
  hawk_user_id: string;

  // Account identity
  account_owner_name: string | null;
  account_owner_email: string | null;
  company_name: string | null;
  plan: string | null;
  trial_start_date: string | null;
  trial_end_date: string | null;
  subscription_start_date: string | null;
  renewal_date: string | null;
  billing_status: string | null;
  mrr: number | null;
  seat_count: number;
  primary_domain: string | null;
  all_domains: string[];

  // Product usage
  total_scans: number;
  scans_this_month: number;
  last_scan_date: string | null;
  features_accessed: Record<string, boolean>;
  reports_generated: number;
  reports_downloaded: number;
  compliance_accessed: boolean;
  agency_accessed: boolean;
  sessions_this_month: number;
  last_login_date: string | null;
  avg_session_minutes: number;
  onboarding_pct: number;
  onboarding_steps_done: string[];

  // Health signals
  nps_score: number | null;
  nps_comment: string | null;
  nps_submitted_at: string | null;
  tickets_open: number;
  tickets_closed_month: number;
  cancellation_intent: boolean;
  cancellation_intent_at: string | null;
  downgrade_requested: boolean;
  upgrade_clicked: boolean;
  payment_failed_count: number;

  // Calculated
  churn_risk_numeric: number;
  churn_risk_label: ChurnRisk;

  synced_at: string;
  created_at: string;
}

export interface OnboardingTask {
  id: string;
  client_id: string;
  csm_rep_id: string | null;
  day_number: number;
  title: string;
  description: string | null;
  due_date: string;
  status: "pending" | "completed" | "skipped" | "overdue";
  completed_at: string | null;
  completed_by: string | null;
  notes: string | null;
  created_at: string;
}

export interface ProductCommand {
  type:
    | "extend_trial"
    | "convert_trial"
    | "change_plan"
    | "grant_feature"
    | "revoke_feature"
    | "pause_account"
    | "reactivate_account"
    | "add_scan_credits"
    | "force_password_reset"
    | "send_notification";
  label: string;
  allowedRoles: UserRole[];
  requiresConfirmation: boolean;
  confirmationMessage?: string;
  destructive?: boolean;
}

// ─── API Response Envelope ─────────────────────────────────────────────────────

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta?: {
    total: number;
    page: number;
    limit: number;
  };
}

/** Audit log row from `auditApi.list` / Supabase `audit_log`. */
export interface AuditLogEntry {
  action: string;
  record_type: string;
  created_at: string;
  user?: { name: string } | null;
}

// ─── Store Types ───────────────────────────────────────────────────────────────

export interface CRMStoreState {
  user: CRMUser | null;
  prospects: Prospect[];
  clients: Client[];
  notifications: Notification[];
  selectedProspect: Prospect | null;
  drawerOpen: boolean;
  sidebarCollapsed: boolean;
  globalSearch: string;
}

export interface LostReasonData {
  reason: string;
  notes: string | null;
  reactivate_at: string | null;
}

export interface CloseWonData {
  plan: ClientPlan;
  mrr: number;
  payment_confirmed: boolean;
  stripe_customer_id?: string;
}
