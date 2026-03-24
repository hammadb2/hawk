import { cn } from "@/lib/utils";

function scoreColor(score: number): string {
  if (score >= 70) return "bg-red-100 text-red-700 border-red-200";
  if (score >= 40) return "bg-yellow-100 text-yellow-700 border-yellow-200";
  return "bg-green-100 text-green-700 border-green-200";
}

export function HawkScoreBadge({ score }: { score: number | null }) {
  if (score === null) {
    return <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-500 border border-gray-200">—</span>;
  }
  return (
    <span className={cn("px-2 py-0.5 rounded text-xs font-bold border", scoreColor(score))}>
      {score}
    </span>
  );
}
