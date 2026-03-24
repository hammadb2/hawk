import { cn } from "@/lib/utils";
import type { ChurnRisk } from "@/lib/crm-types";

const COLORS: Record<ChurnRisk, string> = {
  low: "bg-green-100 text-green-700",
  medium: "bg-yellow-100 text-yellow-700",
  high: "bg-red-100 text-red-700",
};

export function ChurnRiskBadge({ risk }: { risk: ChurnRisk }) {
  return (
    <span className={cn("px-2 py-0.5 rounded text-xs font-medium capitalize", COLORS[risk])}>
      {risk} risk
    </span>
  );
}
