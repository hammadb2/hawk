import type { CrmRole } from "@/lib/crm/types";

export type NavItem = {
  href: string;
  label: string;
  badgeKey?: "pipeline_overdue" | "prospects_uncontacted" | "clients_churn" | "team_flagged" | "tickets_open";
  roles: CrmRole[];
};

export const CRM_NAV: NavItem[] = [
  { href: "/crm/dashboard", label: "Dashboard", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/pipeline", label: "Pipeline", badgeKey: "pipeline_overdue", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/prospects", label: "Prospects", badgeKey: "prospects_uncontacted", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/clients", label: "Clients", badgeKey: "clients_churn", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/scoreboard", label: "Scoreboard", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/ai/replies", label: "Replies", roles: ["ceo", "hos", "team_lead"] },
  { href: "/crm/guarantees", label: "Guarantees", roles: ["ceo", "hos"] },
  { href: "/crm/health", label: "Health", roles: ["ceo", "hos"] },
  { href: "/crm/team", label: "Team", badgeKey: "team_flagged", roles: ["ceo", "hos"] },
  { href: "/crm/reports", label: "Reports", roles: ["ceo", "hos", "team_lead"] },
  { href: "/crm/earnings", label: "Earnings", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/audit-log", label: "Audit log", roles: ["ceo", "hos"] },
  { href: "/crm/settings", label: "Settings", roles: ["ceo"] },
  { href: "/crm/tickets", label: "Support Tickets", badgeKey: "tickets_open", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
];

export function navVisibleForRole(role: CrmRole | undefined) {
  if (!role) return [];
  return CRM_NAV.filter((n) => n.roles.includes(role));
}
