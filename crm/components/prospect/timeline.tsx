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
import { Badge } from "@/components/ui/badge";
import { getSupabaseClient } from "@/lib/supabase";
import type { Activity, ActivityType, EmailEvent, ReplySentiment } from "@/types/crm";

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

function emailEventLabel(t: string): string {
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const SENTIMENT_BADGE: Record<ReplySentiment, string> = {
  positive: "bg-green/15 text-green border-green/30",
  negative: "bg-red/15 text-red border-red/30",
  question: "bg-blue/15 text-blue border-blue/30",
  ooo: "bg-yellow/15 text-yellow border-yellow/30",
};

type MergedRow =
  | { kind: "activity"; id: string; at: string; activity: Activity }
  | { kind: "email"; id: string; at: string; email: EmailEvent };

interface TimelineProps {
  prospectId: string;
}

/** Master spec §02 — unified timeline: rep activities + Charlotte email_events (merged, newest first). */
export function Timeline({ prospectId }: TimelineProps) {
  const [rows, setRows] = useState<MergedRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const supabase = getSupabaseClient();
        const [actRes, mailRes] = await Promise.all([
          supabase
            .from("activities")
            .select("id, type, notes, metadata, created_at, created_by, prospect_id")
            .eq("prospect_id", prospectId)
            .order("created_at", { ascending: false })
            .limit(80),
          supabase
            .from("email_events")
            .select("*")
            .eq("prospect_id", prospectId)
            .order("created_at", { ascending: false })
            .limit(80),
        ]);

        const activities = (actRes.data as Activity[]) ?? [];
        const emails = (mailRes.data as EmailEvent[]) ?? [];

        const merged: MergedRow[] = [
          ...activities.map((a) => ({
            kind: "activity" as const,
            id: `a-${a.id}`,
            at: a.created_at,
            activity: a,
          })),
          ...emails.map((e) => ({
            kind: "email" as const,
            id: `e-${e.id}`,
            at: e.sent_at || e.replied_at || e.created_at,
            email: e,
          })),
        ];

        merged.sort((x, y) => new Date(y.at).getTime() - new Date(x.at).getTime());
        setRows(merged.slice(0, 100));
      } catch {
        setRows([]);
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [prospectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={Phone}
        title="No activity yet"
        description="Charlotte emails, calls, notes, and scans will appear here in one timeline."
      />
    );
  }

  return (
    <div className="space-y-1 py-2">
      {rows.map((row, i) => {
        const isLast = i === rows.length - 1;

        if (row.kind === "email") {
          const e = row.email;
          return (
            <div key={row.id} className="flex gap-3 group">
              <div className="flex flex-col items-center flex-shrink-0">
                <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 bg-accent/10 border border-accent/25">
                  <Mail className="w-3.5 h-3.5 text-accent-light" />
                </div>
                {!isLast && <div className="w-px flex-1 bg-border mt-1 min-h-[16px]" />}
              </div>
              <div className={cn("flex-1 pb-4", isLast && "pb-0")}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-accent-light">Charlotte</span>
                    <span className="text-2xs text-text-dim">·</span>
                    <span className="text-xs text-text-secondary">{emailEventLabel(e.smartlead_event_type)}</span>
                    {e.reply_sentiment && (
                      <Badge
                        variant="secondary"
                        className={cn("text-2xs capitalize border", SENTIMENT_BADGE[e.reply_sentiment])}
                      >
                        {e.reply_sentiment}
                      </Badge>
                    )}
                  </div>
                  <span className="text-2xs text-text-dim flex-shrink-0">{formatDateTime(row.at)}</span>
                </div>
                {e.subject && (
                  <p className="text-xs text-text-secondary mt-1 leading-relaxed">{e.subject}</p>
                )}
                <div className="mt-1 flex flex-wrap gap-2">
                  {e.sequence_step != null && (
                    <span className="text-2xs text-text-dim bg-surface-3 rounded px-1.5 py-0.5">
                      Step {e.sequence_step}
                    </span>
                  )}
                  {e.open_count > 0 && (
                    <span className="text-2xs text-text-dim bg-surface-3 rounded px-1.5 py-0.5">
                      {e.open_count} open{e.open_count !== 1 ? "s" : ""}
                    </span>
                  )}
                  {e.click_count > 0 && (
                    <span className="text-2xs text-text-dim bg-surface-3 rounded px-1.5 py-0.5">
                      {e.click_count} click{e.click_count !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        }

        const activity = row.activity;
        const config = ACTIVITY_CONFIG[activity.type] ?? ACTIVITY_CONFIG.note_added;
        const Icon = config.icon;

        return (
          <div key={row.id} className="flex gap-3 group">
            <div className="flex flex-col items-center flex-shrink-0">
              <div className={cn("w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0", config.bg)}>
                <Icon className={cn("w-3.5 h-3.5", config.color)} />
              </div>
              {!isLast && <div className="w-px flex-1 bg-border mt-1 min-h-[16px]" />}
            </div>

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
