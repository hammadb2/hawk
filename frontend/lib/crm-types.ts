// CRM TypeScript types

export type CRMRole = "ceo" | "head_of_sales" | "team_lead" | "sales_rep" | "charlotte";

export type PipelineStage =
  | "new"
  | "scanned"
  | "loom_sent"
  | "replied"
  | "call_booked"
  | "proposal_sent"
  | "closed_won"
  | "closed_lost";

export const PIPELINE_STAGES: PipelineStage[] = [
  "new",
  "scanned",
  "loom_sent",
  "replied",
  "call_booked",
  "proposal_sent",
  "closed_won",
  "closed_lost",
];

export const STAGE_LABELS: Record<PipelineStage, string> = {
  new: "New",
  scanned: "Scanned",
  loom_sent: "Loom Sent",
  replied: "Replied",
  call_booked: "Call Booked",
  proposal_sent: "Proposal Sent",
  closed_won: "Closed ✓",
  closed_lost: "Lost",
};

export type ChurnRisk = "low" | "medium" | "high";
export type ClientStatus = "active" | "churned";
export type CommissionType = "closing" | "residual";
export type ActivityType = "call" | "email" | "note" | "stage_change" | "loom" | "meeting";
export type TaskPriority = "low" | "medium" | "high";
export type EmailStatus = "sent" | "delivered" | "opened" | "replied" | "bounced";

export interface CRMUser {
  id: string;
  user_id: string;
  crm_role: CRMRole;
  monthly_target: number;
  team_lead_id: string | null;
  is_active: boolean;
  email: string;
  first_name: string | null;
  last_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface CRMUserStats extends CRMUser {
  closes_this_month: number;
  mrr_closed_this_month: number;
  total_prospects: number;
  commission_this_month: number;
}

export interface Prospect {
  id: string;
  company_name: string;
  domain: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  industry: string | null;
  city: string | null;
  stage: PipelineStage;
  hawk_score: number | null;
  assigned_rep_id: string | null;
  assigned_rep_name: string | null;
  source: string;
  notes: string | null;
  estimated_mrr: number | null;
  lost_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Client {
  id: string;
  prospect_id: string | null;
  company_name: string;
  domain: string | null;
  contact_name: string | null;
  contact_email: string | null;
  mrr: number; // cents
  closed_by_rep_id: string | null;
  closed_by_rep_name: string | null;
  closed_at: string | null;
  churn_risk: ChurnRisk;
  churn_risk_reason: string | null;
  status: ClientStatus;
  churned_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Activity {
  id: string;
  prospect_id: string;
  crm_user_id: string | null;
  crm_user_name: string | null;
  activity_type: ActivityType;
  description: string | null;
  old_stage: string | null;
  new_stage: string | null;
  created_at: string;
}

export interface Task {
  id: string;
  crm_user_id: string;
  prospect_id: string | null;
  title: string;
  description: string | null;
  due_date: string | null;
  completed_at: string | null;
  priority: TaskPriority;
  created_at: string;
  updated_at: string;
}

export interface Commission {
  id: string;
  crm_user_id: string;
  client_id: string;
  commission_type: CommissionType;
  amount: number; // cents
  period_start: string | null;
  period_end: string | null;
  paid: boolean;
  created_at: string;
  updated_at: string;
}

export interface CharlotteEmail {
  id: string;
  prospect_id: string;
  to_email: string;
  subject: string | null;
  status: EmailStatus;
  sent_at: string | null;
  opened_at: string | null;
  replied_at: string | null;
  created_at: string;
}

export interface CharlotteStats {
  sent_today: number;
  total_sent: number;
  total_opened: number;
  total_replied: number;
  total_bounced: number;
  open_rate: number;
  reply_rate: number;
}

export interface DashboardStats {
  total_prospects: number;
  closes_this_month: number;
  pipeline_value_cents: number;
  tasks_due_today: number;
  commission_this_month_cents: number;
  total_residual_cents: number;
  // CEO/HoS only
  active_clients?: number;
  churn_risk_count?: number;
  total_mrr_cents?: number;
  mrr_added_this_month_cents?: number;
  charlotte_emails_today?: number;
}

export interface ScoreboardEntry {
  crm_user_id: string;
  name: string;
  email: string;
  role: CRMRole;
  monthly_target: number;
  closes: number;
  commission_cents: number;
  on_pace: boolean | null;
  rank: number;
}
