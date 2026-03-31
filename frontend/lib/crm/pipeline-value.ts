/**
 * Same dollar heuristic as pipeline Kanban (hawk score bands).
 * Used by CEO live dashboard and `pipeline-page` `stageValue` — keep in sync.
 */
export function estimatePipelineValueDollars(hawkScore: number): number {
  if (hawkScore >= 70) return 5000;
  if (hawkScore >= 40) return 2500;
  return 1000;
}

export function sumOpenPipelineValueDollars<T extends { stage: string; hawk_score: number }>(prospects: T[]): number {
  const closed = new Set(["lost", "closed_won"]);
  return prospects.filter((p) => !closed.has(p.stage)).reduce((s, p) => s + estimatePipelineValueDollars(p.hawk_score ?? 0), 0);
}
