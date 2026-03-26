"use client";

import { AlertTriangle, Clock } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatCurrency, getInitials, cn } from "@/lib/utils";
import type { CRMUser } from "@/types/crm";

interface RepCardProps {
  rep: CRMUser;
  performance: {
    closes_this_month: number;
    monthly_target: number;
    conversion_rate: number;
    avg_days_to_close: number;
    commission_earned: number;
    rank: number;
    days_since_last_close: number;
    at_risk_14_day: boolean;
  };
  onAtRiskAction?: (action: "extend_7d" | "begin_removal" | "on_leave") => void;
  canManage?: boolean;
}

export function RepCard({ rep, performance, onAtRiskAction, canManage }: RepCardProps) {
  const progress = (performance.closes_this_month / performance.monthly_target) * 100;

  const dayTrackerColor =
    performance.days_since_last_close <= 7
      ? "text-green bg-green/10"
      : performance.days_since_last_close <= 13
      ? "text-yellow bg-yellow/10"
      : "text-red bg-red/10";

  return (
    <div className={cn(
      "rounded-xl border p-4 transition-all",
      performance.at_risk_14_day
        ? "border-red/30 bg-red/5"
        : "border-border bg-surface-1"
    )}>
      <div className="flex items-start gap-3 mb-3">
        <div className="relative">
          <Avatar className="w-10 h-10">
            <AvatarFallback className="text-sm">{getInitials(rep.name)}</AvatarFallback>
          </Avatar>
          <div className={cn(
            "absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-surface-1",
            rep.status === "active" ? "bg-green" :
            rep.status === "at_risk" ? "bg-yellow" : "bg-red"
          )} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text-primary">{rep.name}</h3>
            {performance.at_risk_14_day && (
              <Badge variant="destructive" className="text-2xs gap-1">
                <AlertTriangle className="w-2.5 h-2.5" />
                14-Day Rule
              </Badge>
            )}
          </div>
          <p className="text-xs text-text-dim capitalize">{rep.role.replace("_", " ")}</p>
        </div>
        <div className={cn("flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-bold", dayTrackerColor)}>
          <Clock className="w-3 h-3" />
          {performance.days_since_last_close}d
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-text-dim">Closes this month</span>
          <span className="font-semibold text-text-primary">
            {performance.closes_this_month}/{performance.monthly_target}
          </span>
        </div>
        <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              progress >= 100 ? "bg-green" :
              performance.at_risk_14_day ? "bg-red" : "bg-accent"
            )}
            style={{ width: `${Math.min(100, progress)}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 mb-3 text-center">
        <div>
          <p className="text-xs font-semibold text-text-primary">{performance.conversion_rate}%</p>
          <p className="text-2xs text-text-dim">Conv. Rate</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-text-primary">{performance.avg_days_to_close}d</p>
          <p className="text-2xs text-text-dim">Avg Close</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-green">{formatCurrency(performance.commission_earned)}</p>
          <p className="text-2xs text-text-dim">Commission</p>
        </div>
      </div>

      {/* At Risk actions */}
      {canManage && performance.at_risk_14_day && onAtRiskAction && (
        <div className="flex items-center gap-2 pt-2 border-t border-border/50">
          <span className="text-xs text-text-dim flex-1">Actions:</span>
          <Button
            variant="secondary"
            size="sm"
            className="h-6 text-2xs px-2"
            onClick={() => onAtRiskAction("extend_7d")}
          >
            Extend 7d
          </Button>
          <Button
            variant="warning"
            size="sm"
            className="h-6 text-2xs px-2"
            onClick={() => onAtRiskAction("on_leave")}
          >
            On Leave
          </Button>
          <Button
            variant="danger"
            size="sm"
            className="h-6 text-2xs px-2"
            onClick={() => onAtRiskAction("begin_removal")}
          >
            Remove
          </Button>
        </div>
      )}
    </div>
  );
}
