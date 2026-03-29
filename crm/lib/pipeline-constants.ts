/** Master spec §01 — heuristic pipeline column value (pre-close ARR proxy). */
export const ESTIMATED_PIPELINE_VALUE_PER_PROSPECT = 149;

/** Master spec §01 — Lost Reason modal options (shared with bulk lost). */
export const LOST_REASON_OPTIONS = [
  "Price too high",
  "No decision maker access",
  "Went with competitor",
  "No budget right now",
  "Not interested",
  "Could not reach after 5 attempts",
  "Other (requires note)",
] as const;

export type LostReasonOption = (typeof LOST_REASON_OPTIONS)[number];
