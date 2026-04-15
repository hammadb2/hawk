import type { CrmRole } from "@/lib/crm/types";

export type NavItem = {
  href: string;
  label: string;
  badgeKey?: "pipeline_overdue" | "prospects_uncontacted" | "clients_churn" | "team_flagged" | "tickets_open" | "va_alerts";
  roles: CrmRole[];
};

export const CRM_NAV: NavItem[] = [
  { href: "/crm/dashboard", label: "Dashboard", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/pipeline", label: "Pipeline", badgeKey: "pipeline_overdue", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/prospects", label: "Prospects", badgeKey: "prospects_uncontacted", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/clients", label: "Clients", badgeKey: "clients_churn", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/scoreboard", label: "Scoreboard", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/charlotte", label: "Charlotte", roles: ["ceo", "hos"] },
  { href: "/crm/charlotte/replies", label: "Replies", roles: ["ceo", "hos", "team_lead"] },
  { href: "/crm/guarantees", label: "Guarantees", roles: ["ceo", "hos"] },
  { href: "/crm/health", label: "Health", roles: ["ceo", "hos"] },
  { href: "/crm/team", label: "Team", badgeKey: "team_flagged", roles: ["ceo", "hos"] },
  { href: "/crm/reports", label: "Reports", roles: ["ceo", "hos", "team_lead"] },
  { href: "/crm/earnings", label: "Earnings", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
  { href: "/crm/audit-log", label: "Audit log", roles: ["ceo", "hos"] },
  { href: "/crm/va/roster", label: "VA Team", badgeKey: "va_alerts", roles: ["ceo", "hos", "team_lead", "va_manager"] },
  { href: "/crm/va/input", label: "VA Daily Input", roles: ["ceo", "hos", "team_lead", "va_manager", "va"] },
  { href: "/crm/va/health", label: "Campaign Health", roles: ["ceo", "hos", "team_lead", "va_manager"] },
  { href: "/crm/va/abtests", label: "A/B Tests", roles: ["ceo", "hos", "team_lead", "va_manager"] },
  { href: "/crm/va/objections", label: "Objection Bank", roles: ["ceo", "hos", "team_lead", "va_manager"] },
  { href: "/crm/va/bonus", label: "Bonus Tracker", roles: ["ceo", "hos", "va_manager"] },
  { href: "/crm/settings", label: "Settings", roles: ["ceo"] },
  { href: "/crm/tickets", label: "Support Tickets", badgeKey: "tickets_open", roles: ["ceo", "hos", "team_lead", "sales_rep"] },
];

export function navVisibleForRole(role: CrmRole | undefined) {
  if (!role) return [];
  return CRM_NAV.filter((n) => n.roles.includes(role));
}
