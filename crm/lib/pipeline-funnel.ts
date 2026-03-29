import type { PipelineStage } from "@/types/crm";
import { stageLabel } from "@/lib/utils";

/** Open pipeline stages (excludes closed_won / lost). */
export const OPEN_PIPELINE_STAGES: PipelineStage[] = [
  "new",
  "scanned",
  "loom_sent",
  "replied",
  "call_booked",
  "proposal_sent",
];

export type FunnelRow = { key: PipelineStage; stage: string; count: number };

export function buildFunnelRowsFromProspects(
  rows: { stage: PipelineStage | string }[] | null | undefined
): FunnelRow[] {
  const byStage: Partial<Record<PipelineStage, number>> = {};
  OPEN_PIPELINE_STAGES.forEach((s) => {
    byStage[s] = 0;
  });
  (rows ?? []).forEach((p) => {
    const s = p.stage as PipelineStage;
    if (OPEN_PIPELINE_STAGES.includes(s)) {
      byStage[s] = (byStage[s] || 0) + 1;
    }
  });
  return OPEN_PIPELINE_STAGES.map((s) => ({
    key: s,
    stage: stageLabel(s),
    count: byStage[s] ?? 0,
  }));
}
