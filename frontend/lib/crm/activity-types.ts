export const ACTIVITY_TYPES = [
  "call_logged",
  "email_sent",
  "stage_changed",
  "scan_run",
  "note_added",
  "loom_sent",
  "task_created",
  "task_completed",
  "hot_lead_flagged",
  "prospect_reassigned",
] as const;

export type ActivityType = (typeof ACTIVITY_TYPES)[number];

export function activityLabel(type: string): string {
  const map: Record<string, string> = {
    call_logged: "Call logged",
    email_sent: "Email sent",
    stage_changed: "Stage changed",
    scan_run: "Scan run",
    note_added: "Note added",
    loom_sent: "Loom sent",
    task_created: "Task created",
    task_completed: "Task completed",
    hot_lead_flagged: "Hot lead flagged",
    prospect_reassigned: "Prospect reassigned",
    duplicate_linked: "Duplicate linked",
  };
  return map[type] ?? type;
}

export function activityColor(type: string): string {
  if (type.includes("call")) return "text-sky-400";
  if (type.includes("email")) return "text-emerald-400";
  if (type.includes("stage")) return "text-amber-400";
  if (type.includes("scan")) return "text-emerald-400";
  if (type.includes("note")) return "text-zinc-300";
  if (type.includes("hot")) return "text-rose-400";
  if (type.includes("duplicate")) return "text-amber-400";
  return "text-zinc-400";
}
