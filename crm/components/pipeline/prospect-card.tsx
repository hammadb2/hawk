"use client";

import { useState } from "react";
import { Phone, FileText, Scan, Star, ExternalLink, Clock } from "lucide-react";
import { cn, formatRelativeTime, agingBorderColor, getInitials } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import type { Prospect } from "@/types/crm";

interface ProspectCardProps {
  prospect: Prospect;
  isDragging?: boolean;
  bulkMode?: boolean;
  bulkSelected?: boolean;
  onBulkToggle?: (id: string) => void;
}

export function ProspectCard({
  prospect,
  isDragging,
  bulkMode,
  bulkSelected,
  onBulkToggle,
}: ProspectCardProps) {
  const { setSelectedProspect, setDrawerOpen, updateProspect } = useCRMStore();
  const [hovering, setHovering] = useState(false);
  const [hotLoading, setHotLoading] = useState(false);

  const agingClass = agingBorderColor(prospect.last_activity_at);
  const hasAgingWarning = agingClass !== "border-transparent";

  const handleMarkHot = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setHotLoading(true);
    try {
      const result = await prospectsApi.markHot(prospect.id, !prospect.is_hot);
      if (result.success && result.data) {
        updateProspect(prospect.id, { is_hot: !prospect.is_hot });
        toast({
          title: prospect.is_hot ? "Removed from hot leads" : "Marked as hot lead",
          variant: prospect.is_hot ? "default" : "success",
        });
      }
    } catch {
      toast({ title: "Failed to update hot status", variant: "destructive" });
    } finally {
      setHotLoading(false);
    }
  };

  const handleOpenDrawer = () => {
    if (bulkMode) {
      onBulkToggle?.(prospect.id);
      return;
    }
    setSelectedProspect(prospect);
    setDrawerOpen(true);
  };

  return (
    <div
      onClick={handleOpenDrawer}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      className={cn(
        "rounded-xl border bg-surface-2 p-3.5 cursor-pointer transition-all select-none",
        "hover:border-accent/40 hover:bg-surface-3",
        isDragging ? "shadow-2xl opacity-90 rotate-1 scale-105" : "shadow-sm",
        hasAgingWarning ? agingClass : "border-border",
        bulkSelected && "ring-2 ring-accent/50 border-accent/40"
      )}
    >
      {prospect.duplicate_of && (
        <p className="text-2xs font-medium text-yellow mb-1.5">Possible duplicate — review merge</p>
      )}
      <div className="flex items-start gap-2.5">
        {bulkMode && (
          <div
            className="pt-0.5"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <Checkbox
              checked={bulkSelected}
              onCheckedChange={() => onBulkToggle?.(prospect.id)}
              aria-label={`Select ${prospect.company_name}`}
            />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            {prospect.is_hot && <Star className="w-3 h-3 text-yellow fill-yellow flex-shrink-0" />}
            <p className="text-sm font-semibold text-text-primary truncate">{prospect.company_name}</p>
          </div>
          <a
            href={`https://${prospect.domain}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-text-dim hover:text-accent-light transition-colors flex items-center gap-1"
          >
            {prospect.domain}
            <ExternalLink className="w-2.5 h-2.5" />
          </a>
        </div>
        <HawkScoreRing score={prospect.hawk_score} size="sm" />
      </div>

      <div className="flex items-center gap-2 mt-2.5">
        {prospect.source === "charlotte" && (
          <Badge variant="default" className="text-2xs px-1.5 py-0">
            Charlotte
          </Badge>
        )}
        {prospect.city && (
          <span className="text-2xs text-text-dim">{prospect.city}</span>
        )}
        {hasAgingWarning && (
          <div className="flex items-center gap-1 ml-auto">
            <Clock className={cn(
              "w-3 h-3",
              agingClass.includes("red") ? "text-red" : "text-yellow"
            )} />
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-2.5">
        <div className="flex items-center gap-1.5">
          {prospect.assigned_rep && (
            <Avatar className="w-5 h-5">
              <AvatarFallback className="text-2xs">
                {getInitials(prospect.assigned_rep.name)}
              </AvatarFallback>
            </Avatar>
          )}
          <span className="text-2xs text-text-dim">
            {formatRelativeTime(prospect.last_activity_at)}
          </span>
        </div>

        {/* Quick actions on hover */}
        {hovering && (
          <div
            className="flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedProspect(prospect);
                setDrawerOpen(true);
              }}
              className="p-1 rounded text-text-dim hover:text-blue hover:bg-blue/10 transition-all"
              title="Log Call"
            >
              <Phone className="w-3 h-3" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSelectedProspect(prospect);
                setDrawerOpen(true);
              }}
              className="p-1 rounded text-text-dim hover:text-green hover:bg-green/10 transition-all"
              title="Run Scan"
            >
              <Scan className="w-3 h-3" />
            </button>
            <button
              onClick={handleMarkHot}
              disabled={hotLoading}
              className={cn(
                "p-1 rounded transition-all",
                prospect.is_hot
                  ? "text-yellow hover:text-yellow/60"
                  : "text-text-dim hover:text-yellow hover:bg-yellow/10"
              )}
              title={prospect.is_hot ? "Remove hot" : "Mark Hot"}
            >
              <Star className={cn("w-3 h-3", prospect.is_hot && "fill-yellow")} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
