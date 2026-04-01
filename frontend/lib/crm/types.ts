export type CrmRole = "ceo" | "hos" | "team_lead" | "sales_rep";

export type ProspectStage =
  | "new"
  | "scanned"
  | "loom_sent"
  | "replied"
  | "call_booked"
  | "proposal_sent"
  | "closed_won"
  | "lost";

export type ProspectSource = "charlotte" | "manual" | "inbound";

export type ProfileStatus = "invited" | "onboarding" | "active" | "at_risk" | "inactive";

export type Profile = {
  id: string;
  email: string | null;
  full_name: string | null;
  role: CrmRole;
  team_lead_id: string | null;
  avatar_url: string | null;
  status: ProfileStatus | string;
  created_at: string;
  monthly_close_target?: number | null;
  last_close_at?: string | null;
  onboarding_checklist?: Record<string, boolean> | null;
  onboarding_completed_at?: string | null;
  last_assigned_at?: string | null;
  whatsapp_number?: string | null;
};

export type Prospect = {
  id: string;
  domain: string;
  company_name: string | null;
  industry: string | null;
  city: string | null;
  stage: ProspectStage;
  assigned_rep_id: string | null;
  hawk_score: number;
  source: ProspectSource;
  created_at: string;
  last_activity_at: string;
  is_hot: boolean;
  duplicate_of: string | null;
  lost_reason?: string | null;
  lost_notes?: string | null;
  reactivate_on?: string | null;
  consent_basis?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  phone?: string | null;
};

export type CrmActivityRow = {
  id: string;
  prospect_id: string | null;
  type: string;
  created_by: string | null;
  notes: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type ProspectNoteRow = {
  id: string;
  prospect_id: string;
  author_id: string;
  body: string;
  created_at: string;
  updated_at: string;
};

export type CrmProspectScanRow = {
  id: string;
  prospect_id: string;
  hawk_score: number | null;
  grade: string | null;
  findings: Record<string, unknown> | null;
  status: string;
  created_at: string;
  triggered_by?: string | null;
  scan_version?: string | null;
  industry?: string | null;
  raw_layers?: Record<string, unknown> | null;
  interpreted_findings?: unknown[] | null;
  breach_cost_estimate?: Record<string, unknown> | null;
  external_job_id?: string | null;
  attack_paths?: unknown[] | null;
};

export type ProspectEmailEventRow = {
  id: string;
  prospect_id: string;
  subject: string | null;
  sent_at: string | null;
  opened_at: string | null;
  clicked_at: string | null;
  replied_at: string | null;
  sequence_step: number | null;
  created_at: string;
  /** Phase 3+ columns; optional until migration applied */
  source?: string;
  external_id?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type CrmCommissionRow = {
  id: string;
  client_id: string;
  rep_id: string;
  basis_mrr_cents: number;
  amount_cents: number;
  rate: number;
  status: "pending" | "approved" | "paid";
  created_at: string;
};

export type CrmSupportTicketRow = {
  id: string;
  subject: string;
  body: string;
  status: "open" | "in_progress" | "resolved" | "closed";
  priority: "low" | "normal" | "high";
  requester_id: string;
  created_at: string;
  updated_at: string;
};

export type CrmNotificationRow = {
  id: string;
  user_id: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
  read: boolean;
  link: string | null;
  created_at: string;
};

export type SystemHealthLogRow = {
  id: string;
  service: string;
  status: "ok" | "degraded" | "failed";
  response_ms: number | null;
  checked_at: string;
  detail: Record<string, unknown>;
  alert_sent: boolean;
};

export type CrmClientRow = {
  id: string;
  prospect_id: string | null;
  company_name: string | null;
  domain: string | null;
  plan: string | null;
  mrr_cents: number;
  stripe_customer_id: string | null;
  closing_rep_id: string | null;
  status: "active" | "past_due" | "churned";
  close_date: string;
  created_at: string;
  commission_deferred?: boolean;
};

export type ProspectFileRow = {
  id: string;
  prospect_id: string;
  title: string;
  file_url: string;
  kind: string | null;
  created_at: string;
};

export const STAGE_ORDER: ProspectStage[] = [
  "new",
  "scanned",
  "loom_sent",
  "replied",
  "call_booked",
  "proposal_sent",
  "closed_won",
  "lost",
];

export const STAGE_META: Record<
  ProspectStage,
  { label: string; color: string; columnBg: string }
> = {
  new: { label: "New", color: "#9090A8", columnBg: "rgba(144,144,168,0.12)" },
  scanned: { label: "Scanned", color: "#60A5FA", columnBg: "rgba(96,165,250,0.12)" },
  loom_sent: { label: "Loom Sent", color: "#9B7FFF", columnBg: "rgba(155,127,255,0.12)" },
  replied: { label: "Replied", color: "#2DD4BF", columnBg: "rgba(45,212,191,0.12)" },
  call_booked: { label: "Call Booked", color: "#FBBF24", columnBg: "rgba(251,191,36,0.12)" },
  proposal_sent: { label: "Proposal Sent", color: "#FB923C", columnBg: "rgba(251,146,60,0.12)" },
  closed_won: { label: "Closed Won", color: "#00C48C", columnBg: "rgba(0,196,140,0.12)" },
  lost: { label: "Lost", color: "#FF4757", columnBg: "rgba(255,71,87,0.12)" },
};

export const LOST_REASONS = [
  "Price too high",
  "No decision maker access",
  "Went with competitor",
  "No budget right now",
  "Not interested",
  "Could not reach after 5 attempts",
  "Other",
] as const;

export type LostReason = (typeof LOST_REASONS)[number];

export const PLAN_OPTIONS = [
  { id: "starter", label: "Starter ($199/mo)", mrrCents: 19900 },
  { id: "shield", label: "Shield ($997/mo)", mrrCents: 99700 },
  { id: "enterprise", label: "Enterprise ($2,500/mo)", mrrCents: 250000 },
  { id: "custom", label: "Custom", mrrCents: 0 },
] as const;
