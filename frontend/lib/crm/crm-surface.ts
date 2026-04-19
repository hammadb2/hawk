/**
 * Shared dark surfaces for /crm — keep main content off pure white.
 */
export const crmSurfaceCard = "rounded-xl border border-[#1e1e2e] bg-[#111118]";

export const crmTableWrap = `${crmSurfaceCard} overflow-hidden`;

export const crmTableThead =
  "border-b border-[#1e1e2e] bg-[#0d0d14] text-xs uppercase tracking-wide text-slate-400";

export const crmTableRow = "border-b border-[#1e1e2e]/90 hover:bg-[#1a1a24]";

export const crmEmptyState = `${crmSurfaceCard} px-4 py-10 text-center text-sm text-slate-400`;

export const crmPageTitle = "text-2xl font-semibold text-white";

export const crmPageSubtitle = "mt-1 text-sm text-slate-400";

/** Inputs / nested panels inside dark cards */
export const crmFieldSurface =
  "rounded-lg border border-[#1e1e2e] bg-[#0d0d14] text-slate-200 placeholder:text-slate-500";

/** Modal / drawer shell (replaces default shadcn white in CRM) */
export const crmDialogSurface = "border-[#1e1e2e] bg-[#111118] text-slate-200";
