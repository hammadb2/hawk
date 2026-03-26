import { createClient } from "@/lib/supabase";
import type { CRMUser, UserRole, Prospect, Client } from "@/types/crm";

// ─── Client-side auth helpers ─────────────────────────────────────────────────

export async function getSession() {
  const supabase = createClient();
  const { data, error } = await supabase.auth.getSession();
  if (error) {
    console.error("getSession error:", error.message);
    return null;
  }
  return data.session;
}

export async function getUser(): Promise<CRMUser | null> {
  const supabase = createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) return null;

  const { data, error } = await supabase
    .from("users")
    .select("*, team_lead:team_lead_id(id, name, email, role)")
    .eq("id", user.id)
    .single();

  if (error || !data) {
    console.error("getUser profile error:", error?.message);
    return null;
  }

  return data as CRMUser;
}

export async function getRole(): Promise<UserRole | null> {
  const user = await getUser();
  return user?.role ?? null;
}

// ─── Role checks ──────────────────────────────────────────────────────────────

export function requireRole(role: UserRole, user: CRMUser): void {
  const hierarchy: Record<UserRole, number> = {
    ceo: 5,
    hos: 4,
    team_lead: 3,
    csm: 2,
    rep: 1,
  };

  if (hierarchy[user.role] < hierarchy[role]) {
    throw new Error(
      `Access denied: requires ${role} role, but user has ${user.role} role`
    );
  }
}

export function hasRole(
  user: CRMUser,
  ...roles: UserRole[]
): boolean {
  return roles.includes(user.role);
}

export function isCEO(user: CRMUser): boolean {
  return user.role === "ceo";
}

export function isHoS(user: CRMUser): boolean {
  return user.role === "hos";
}

export function isTeamLead(user: CRMUser): boolean {
  return user.role === "team_lead";
}

export function isRep(user: CRMUser): boolean {
  return user.role === "rep";
}

export function canManageTeam(user: CRMUser): boolean {
  return hasRole(user, "ceo", "hos");
}

export function canViewAllPipeline(user: CRMUser): boolean {
  return hasRole(user, "ceo", "hos", "team_lead");
}

export function canAccessCharlotte(user: CRMUser): boolean {
  return hasRole(user, "ceo", "hos");
}

export function canAccessSettings(user: CRMUser): boolean {
  return isCEO(user);
}

export function canAccessTickets(user: CRMUser): boolean {
  return isCEO(user);
}

export function canViewReports(user: CRMUser): boolean {
  return hasRole(user, "ceo", "hos", "team_lead");
}

// ─── RLS logic for UI guards ──────────────────────────────────────────────────

export function canViewProspect(user: CRMUser, prospect: Prospect): boolean {
  if (hasRole(user, "ceo", "hos")) return true;
  if (isTeamLead(user)) {
    // Can view if prospect is assigned to one of their reps (check done via data layer)
    return true;
  }
  return prospect.assigned_rep_id === user.id;
}

export function canEditProspect(user: CRMUser, prospect: Prospect): boolean {
  if (hasRole(user, "ceo", "hos")) return true;
  if (isTeamLead(user)) return true;
  return prospect.assigned_rep_id === user.id;
}

export function canReassignProspect(user: CRMUser): boolean {
  return hasRole(user, "ceo", "hos");
}

export function canViewClient(user: CRMUser, client: Client): boolean {
  if (hasRole(user, "ceo", "hos")) return true;
  return (
    client.closing_rep_id === user.id || client.csm_rep_id === user.id
  );
}

export function canViewCommission(
  user: CRMUser,
  repId: string
): boolean {
  if (hasRole(user, "ceo", "hos")) return true;
  return user.id === repId;
}
