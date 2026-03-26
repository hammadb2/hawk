import { hawkScoreColor } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface HawkScoreRingProps {
  score: number | null;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
}

export function HawkScoreRing({
  score,
  size = "md",
  showLabel = false,
  className,
}: HawkScoreRingProps) {
  const sizes = {
    sm: { ring: 32, stroke: 3, font: "text-[9px]" },
    md: { ring: 44, stroke: 4, font: "text-xs" },
    lg: { ring: 64, stroke: 5, font: "text-sm" },
  };

  const { ring, stroke, font } = sizes[size];
  const radius = (ring - stroke * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = score !== null ? (score / 100) * circumference : 0;
  const color = score !== null ? hawkScoreColor(score) : "#5C5876";

  if (score === null) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-full bg-surface-3 border border-border",
          className
        )}
        style={{ width: ring, height: ring }}
      >
        <span className={cn("text-text-dim font-mono", font)}>–</span>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col items-center gap-1", className)}>
      <div className="relative" style={{ width: ring, height: ring }}>
        <svg
          width={ring}
          height={ring}
          viewBox={`0 0 ${ring} ${ring}`}
          className="-rotate-90"
        >
          {/* Background track */}
          <circle
            cx={ring / 2}
            cy={ring / 2}
            r={radius}
            fill="none"
            stroke="#1A1727"
            strokeWidth={stroke}
          />
          {/* Progress arc */}
          <circle
            cx={ring / 2}
            cy={ring / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeDasharray={circumference}
            strokeDashoffset={circumference - progress}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.5s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className={cn("font-bold font-mono", font)}
            style={{ color }}
          >
            {score}
          </span>
        </div>
      </div>
      {showLabel && (
        <span className="text-2xs font-medium" style={{ color }}>
          {score >= 70 ? "High Risk" : score >= 40 ? "Medium" : "Low Risk"}
        </span>
      )}
    </div>
  );
}
