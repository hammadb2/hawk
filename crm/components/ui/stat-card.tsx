import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  trend?: {
    value: number;
    label?: string;
  };
  accent?: boolean;
  className?: string;
  onClick?: () => void;
}

export function StatCard({
  label,
  value,
  subValue,
  trend,
  accent,
  className,
  onClick,
}: StatCardProps) {
  const trendPositive = trend && trend.value > 0;
  const trendNeutral = trend && trend.value === 0;

  return (
    <div
      className={cn(
        "rounded-xl border p-4 transition-all",
        accent
          ? "border-accent/30 bg-accent/5"
          : "border-border bg-surface-1",
        onClick && "cursor-pointer hover:border-accent/40 hover:bg-surface-2",
        className
      )}
      onClick={onClick}
    >
      <p className="text-xs font-medium text-text-dim mb-1">{label}</p>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className={cn(
            "text-2xl font-bold tracking-tight",
            accent ? "text-accent-light" : "text-text-primary"
          )}>
            {value}
          </p>
          {subValue && (
            <p className="text-xs text-text-dim mt-0.5">{subValue}</p>
          )}
        </div>
        {trend !== undefined && (
          <div
            className={cn(
              "flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-md",
              trendNeutral
                ? "text-text-dim bg-surface-3"
                : trendPositive
                ? "text-green bg-green/10"
                : "text-red bg-red/10"
            )}
          >
            {trendNeutral ? (
              <Minus className="w-3 h-3" />
            ) : trendPositive ? (
              <TrendingUp className="w-3 h-3" />
            ) : (
              <TrendingDown className="w-3 h-3" />
            )}
            <span>
              {trendPositive ? "+" : ""}
              {trend.value}%{trend.label ? ` ${trend.label}` : ""}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
