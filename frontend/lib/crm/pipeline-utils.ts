import type { ProspectStage } from "@/lib/crm/types";
import { STAGE_ORDER } from "@/lib/crm/types";

export function agingBorderClass(lastActivityAt: string, now: number = Date.now()): string {
  const days = (now - new Date(lastActivityAt).getTime()) / (1000 * 60 * 60 * 24);
  if (days >= 14) return "border-2 border-red-500 shadow-[0_0_0_1px_rgba(239,68,68,0.35)]";
  if (days >= 7) return "border-2 border-amber-400 shadow-[0_0_0_1px_rgba(251,191,36,0.25)]";
  return "border border-[#1e1e2e]";
}

export function bottleneckStage(counts: Record<ProspectStage, number>): ProspectStage | null {
  for (let i = 0; i < STAGE_ORDER.length - 1; i++) {
    const a = STAGE_ORDER[i];
    const b = STAGE_ORDER[i + 1];
    const ca = counts[a];
    const cb = counts[b];
    if (ca < 3) continue;
    if (cb === 0 && ca >= 3) return a;
    if (cb > 0 && ca >= 3 * cb) return a;
  }
  return null;
}
