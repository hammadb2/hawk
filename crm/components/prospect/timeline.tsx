"use client";

import { useState, useEffect } from "react";
import {
  Phone,
  Mail,
  ArrowRight,
  Shield,
  Pen,
  Video,
  CheckSquare,
  Check,
  Star,
  User,
  TrendingUp,
} from "lucide-react";
import { cn, formatDateTime, getInitials } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { getSupabaseClient } from "@/lib/supabase";
import type { Activity, ActivityType } from "@/types/crm";

const ACTIVITY_CONFIG: Record<
  ActivityType,
  { icon: typeof Phone; color: string; bg: string; label: string }
> = {
  call: { icon: Phone, color: "text-blue", bg: "bg-blue/10", label: "Call" },
  email_sent: { icon: Mail, color: "text-accent-light", bg: "bg-accent/10", label: "Email Sent" },
  stage_changed: { icon: ArrowRight, color: "text-text-secondary", bg: "bg-surface-3", label: "Stage Changed" },
  scan_run: { icon: Shield, color: "text-green", bg: "bg-green/10", label: "Scan Run" },
  note_added: { icon: Pen, color: "text-yellow", bg: "bg-yellow/10", label: "Note Added" },
  loom_sent: { icon: Video, color: "text-[#2DD4BF]", bg: "bg-[#2DD4BF]/10", label: "Loom Sent" },
  task_created: { icon: CheckSquare, color: "text-text-secondary", bg: "bg-surface-3", label: "Task Created" },
  task_completed: { icon: Check, color: "text-green", bg: "bg-green/10", label: "Task Completed" },
  hot_flagged: { icon: Star, color: "text-yellow", bg: "bg-yellow/10", label: "Hot Flagged" },
  reassigned: { icon: User, color: "text-text-secondary", bg: "bg-surface-3", label: "Reassigned" },
  close_won: { icon: TrendingUp, color: "text-green", bg: "bg-green/10", label: "Closed Won" },
};

interface TimelineProps {
  prospectId: string;
}

export function Timeline({ prospectId }: TimelineProps) {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const supabase = getSupabaseClient();
        const { data } = await supabase
          .from("activities")
          .select("id, type, notes, metadata, created_at, created_by, prospect_id")
          .eq("prospect_id", prospectId)
          .order("created_at", { ascending: false })
          .limit(50);

        if (data) {
          setActivities(data as Activity[]);
        }
      } catch {
        // fail silently
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [prospectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  if (activities.length === 0) {
    return (
      <EmptyState
        icon={Phone}
        title="No activity yet"
        description="Log a call, add a note, or run a scan to get started."
      />
    );
  }

  return (
    <div className="space-y-1 py-2">
      {activities.map((activity, i) => {
        const config = ACTIVITY_CONFIG[activity.type] ?? ACTIVITY_CONFIG.note_added;
        const Icon = config.icon;
        const isLast = i === activities.length - 1;

        return (
          <div key={activity.id} className="flex gap-3 group">
            {/* Timeline line */}
            <div className="flex flex-col items-center flex-shrink-0">
              <div className={cn("w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0", config.bg)}>
                <Icon className={cn("w-3.5 h-3.5", config.color)} />
              </div>
              {!isLast && <div className="w-px flex-1 bg-border mt-1 min-h-[16px]" />}
            </div>

            {/* Content */}
            <div className={cn("flex-1 pb-4", isLast && "pb-0")}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  {activity.author && (
                    <Avatar className="w-4 h-4">
                      <AvatarFallback className="text-2xs">{getInitials(activity.author.name)}</AvatarFallback>
                    </Avatar>
                  )}
                  <span className={cn("text-xs font-medium", config.color)}>{config.label}</span>
                  {activity.author && (
                    <span className="text-2xs text-text-dim">by {activity.author.name}</span>
                  )}
                </div>
                <span className="text-2xs text-text-dim flex-shrink-0">
                  {formatDateTime(activity.created_at)}
                </span>
              </div>

              {activity.notes && (
                <p className="text-xs text-text-secondary mt-1 leading-relaxed">{activity.notes}</p>
              )}

              {activity.metadata && Object.keys(activity.metadata).length > 0 && (
                <div className="mt-1 flex flex-wrap gap-2">
                  {activity.type === "call" && !!activity.metadata.outcome && (
                    <span className="text-2xs text-text-dim bg-surface-3 rounded px-1.5 py-0.5 capitalize">
                      {String(activity.metadata.outcome)}
                    </span>
                  )}
                  {activity.type === "call" && !!activity.metadata.duration_minutes && (
                    <span className="text-2xs text-text-dim bg-surface-3 rounded px-1.5 py-0.5">
                      {String(activity.metadata.duration_minutes)} min
                    </span>
                  )}
                  {activity.type === "stage_changed" && (
                    <span className="text-2xs text-text-dim">
                      → {String(activity.metadata.to_stage ?? "")}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
