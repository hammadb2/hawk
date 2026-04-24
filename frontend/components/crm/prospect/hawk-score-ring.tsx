"use client";

import { cn } from "@/lib/utils";

export function HawkScoreRing({
  score,
  size = 72,
  className,
  showEmptyState = true,
}: {
  score: number;
  size?: number;
  className?: string;
  /**
   * When true (default), treats score=0/null as "not scanned yet" and renders
   * a muted ring with "—". Callers rendering a specific completed scan result
   * should pass `false` so a legitimate score of 0 still renders with its red
   * ring + the `0` number.
   */
  showEmptyState?: boolean;
}) {
  const stroke = 6;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const hasScore = showEmptyState ? typeof score === "number" && score > 0 : true;
  const clamped = Math.min(100, Math.max(0, score || 0));
  const pct = clamped / 100;
  const offset = c * (1 - pct);
  const color = !hasScore
    ? "#64748b" // slate-500 muted ring for unscanned (score null/0)
    : clamped < 40
      ? "#f87171"
      : clamped < 70
        ? "#fbbf24"
        : "#34d399";
  return (
    <div
      className={cn("relative shrink-0", className)}
      style={{ width: size, height: size }}
      title={
        hasScore
          ? `HAWK score ${clamped}/100 — red under 40, amber 40–70, green above 70`
          : "Not scanned yet"
      }
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-ink-100/60"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={hasScore ? offset : c}
          className="transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm font-semibold text-white">
        {hasScore ? clamped : "—"}
      </div>
    </div>
  );
}
