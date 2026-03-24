import { cn } from "@/lib/utils";
import { STAGE_LABELS, type PipelineStage } from "@/lib/crm-types";

const STAGE_COLORS: Record<PipelineStage, string> = {
  new: "bg-gray-100 text-gray-700",
  scanned: "bg-blue-100 text-blue-700",
  loom_sent: "bg-purple-100 text-purple-700",
  replied: "bg-yellow-100 text-yellow-700",
  call_booked: "bg-orange-100 text-orange-700",
  proposal_sent: "bg-indigo-100 text-indigo-700",
  closed_won: "bg-green-100 text-green-700",
  closed_lost: "bg-red-100 text-red-700",
};

export function StageBadge({ stage }: { stage: PipelineStage }) {
  return (
    <span className={cn("px-2 py-0.5 rounded text-xs font-medium", STAGE_COLORS[stage])}>
      {STAGE_LABELS[stage] || stage}
    </span>
  );
}
