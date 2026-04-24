"use client";

/** Readiness score history from `hawk_guarantee_events` — SVG sparkline, no extra chart deps. */

export function ReadinessSparkline({
  points,
}: {
  points: { score: number; at: string }[];
}) {
  if (points.length < 2) return null;
  const w = 220;
  const h = 44;
  const pad = 4;
  const vals = points.map((p) => p.score);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = Math.max(1, max - min);
  const normY = (v: number) => {
    if (max === min) return h / 2;
    return h - pad - ((v - min) / span) * (h - 2 * pad);
  };
  const path = points
    .map((p, i) => {
      const x = pad + (i / (points.length - 1)) * (w - 2 * pad);
      const y = normY(p.score);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="mt-3 w-full">
      <p className="text-[10px] font-medium uppercase tracking-wide text-ink-0">Readiness history</p>
      <svg
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        className="mt-1 text-signal"
        role="img"
        aria-label="Readiness score over time"
      >
        <path d={path} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="mt-1 text-[10px] text-ink-0">
        From guarantee monitoring events. More points appear as Shield scans update your score.
      </p>
    </div>
  );
}
