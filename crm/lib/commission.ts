import type { UserRole, ClientPlan } from "@/types/crm";

// ─── Commission Rates ─────────────────────────────────────────────────────────

export const COMMISSION_RATES = {
  rep_closing: 0.30,            // 30% of first month
  rep_residual: 0.10,           // 10% monthly per active client
  tl_personal: 0.20,            // Team Lead own closes
  tl_override: 0.05,            // TL on rep closes
  tl_residual_override: 0.03,   // TL on team residuals
  hos_override: 0.03,           // HoS on all org closes
  hos_residual_override: 0.02,  // HoS on all residuals
} as const;

// ─── Plan Values ──────────────────────────────────────────────────────────────

export const PLAN_VALUES: Record<ClientPlan, number> = {
  starter: 99,
  shield: 199,
  enterprise: 399,
  custom: 0, // Set manually
};

// ─── Bonus Tiers ──────────────────────────────────────────────────────────────

export const BONUS_TIERS = [
  { closes: 5, bonus: 250 },
  { closes: 10, bonus: 750 },
  { closes: 15, bonus: 1500 },
  { closes: 20, bonus: 2000 },
] as const;

// ─── Clawback Config ─────────────────────────────────────────────────────────

export const DEFAULT_CLAWBACK_WINDOW_DAYS = 90;

// ─── Calculation Functions ────────────────────────────────────────────────────

/**
 * Calculate closing commission for a given role and plan value.
 * @param role - The user's role
 * @param planValue - Monthly plan value in CAD
 * @param isOwnClose - Whether this is the rep's own close (vs override)
 */
export function calculateClosingCommission(
  role: UserRole,
  planValue: number,
  isOwnClose: boolean
): number {
  switch (role) {
    case "rep":
      return planValue * COMMISSION_RATES.rep_closing;
    case "team_lead":
      if (isOwnClose) {
        return planValue * COMMISSION_RATES.tl_personal;
      }
      return planValue * COMMISSION_RATES.tl_override;
    case "hos":
      return planValue * COMMISSION_RATES.hos_override;
    case "ceo":
      return 0; // CEO doesn't earn individual commissions
    default:
      return 0;
  }
}

/**
 * Calculate monthly residual commission.
 * @param role - The user's role
 * @param clientMRR - Monthly recurring revenue
 */
export function calculateResidualCommission(
  role: UserRole,
  clientMRR: number
): number {
  switch (role) {
    case "rep":
      return clientMRR * COMMISSION_RATES.rep_residual;
    case "team_lead":
      return clientMRR * COMMISSION_RATES.tl_residual_override;
    case "hos":
      return clientMRR * COMMISSION_RATES.hos_residual_override;
    case "ceo":
      return 0;
    default:
      return 0;
  }
}

/**
 * Determine if a commission should be clawed back.
 * @param closeDate - The date the deal was closed
 * @param cancelDate - The date the client cancelled
 * @param clawbackWindowDays - Number of days in clawback window
 */
export function checkClawback(
  closeDate: Date,
  cancelDate: Date,
  clawbackWindowDays: number = DEFAULT_CLAWBACK_WINDOW_DAYS
): boolean {
  const diffMs = cancelDate.getTime() - closeDate.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  return diffDays < clawbackWindowDays;
}

/**
 * Calculate days remaining in clawback window.
 * @param closeDate - The date the deal was closed
 * @param clawbackWindowDays - Number of days in clawback window
 */
export function clawbackDaysRemaining(
  closeDate: Date,
  clawbackWindowDays: number = DEFAULT_CLAWBACK_WINDOW_DAYS
): number {
  const deadline = new Date(closeDate);
  deadline.setDate(deadline.getDate() + clawbackWindowDays);
  const now = new Date();
  const diffMs = deadline.getTime() - now.getTime();
  return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
}

/**
 * Calculate next bonus tier info.
 * @param closesThisMonth - Number of closes this month
 */
export function getNextBonusTier(closesThisMonth: number): {
  nextTier: (typeof BONUS_TIERS)[number] | null;
  closesNeeded: number;
  progress: number;
} {
  const nextTier = BONUS_TIERS.find((t) => t.closes > closesThisMonth) ?? null;

  if (!nextTier) {
    const lastTier = BONUS_TIERS[BONUS_TIERS.length - 1];
    return {
      nextTier: null,
      closesNeeded: 0,
      progress: Math.min(100, (closesThisMonth / lastTier.closes) * 100),
    };
  }

  const prevTier = BONUS_TIERS.find((t) => t.closes <= closesThisMonth);
  const prevCloses = prevTier?.closes ?? 0;
  const progress =
    ((closesThisMonth - prevCloses) / (nextTier.closes - prevCloses)) * 100;

  return {
    nextTier,
    closesNeeded: nextTier.closes - closesThisMonth,
    progress: Math.min(100, progress),
  };
}

/**
 * Calculate total commissions for a rep in a month.
 */
export function calculateMonthlyTotal(commissions: Array<{ amount: number; type: string }>): {
  closing: number;
  residual: number;
  bonus: number;
  override: number;
  clawback: number;
  net: number;
} {
  const result = {
    closing: 0,
    residual: 0,
    bonus: 0,
    override: 0,
    clawback: 0,
    net: 0,
  };

  for (const c of commissions) {
    switch (c.type) {
      case "closing":
        result.closing += c.amount;
        break;
      case "residual":
        result.residual += c.amount;
        break;
      case "bonus":
        result.bonus += c.amount;
        break;
      case "override":
        result.override += c.amount;
        break;
      case "clawback":
        result.clawback += c.amount;
        break;
    }
  }

  result.net =
    result.closing +
    result.residual +
    result.bonus +
    result.override -
    result.clawback;

  return result;
}
