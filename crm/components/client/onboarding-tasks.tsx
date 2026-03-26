"use client";

import { useState } from "react";
import { CheckCircle2, Clock, AlertCircle, SkipForward } from "lucide-react";
import { OnboardingTask } from "@/types/crm";
import { createClient } from "@/lib/supabase";
import { cn, formatDate } from "@/lib/utils";

interface OnboardingTasksProps {
  clientId: string;
  tasks: OnboardingTask[];
  onUpdate?: () => void;
}

const STATUS_CONFIG = {
  pending:   { icon: <Clock className="w-4 h-4" />,        color: "text-text-dim",    label: "Pending" },
  completed: { icon: <CheckCircle2 className="w-4 h-4" />, color: "text-green-400",   label: "Done" },
  overdue:   { icon: <AlertCircle className="w-4 h-4" />,  color: "text-red-400",     label: "Overdue" },
  skipped:   { icon: <SkipForward className="w-4 h-4" />,  color: "text-text-dim",    label: "Skipped" },
};

export function OnboardingTasks({ tasks, onUpdate }: OnboardingTasksProps) {
  const [loading, setLoading] = useState<string | null>(null);

  const completed = tasks.filter((t) => t.status === "completed").length;
  const total = tasks.length;
  const pct = total ? Math.round((completed / total) * 100) : 0;

  async function markDone(task: OnboardingTask) {
    if (task.status === "completed") return;
    setLoading(task.id);
    try {
      const sb = createClient();
      await sb.from("onboarding_tasks").update({
        status: "completed",
        completed_at: new Date().toISOString(),
      }).eq("id", task.id);
      onUpdate?.();
    } finally {
      setLoading(null);
    }
  }

  async function markSkipped(task: OnboardingTask) {
    setLoading(task.id);
    try {
      const sb = createClient();
      await sb.from("onboarding_tasks").update({ status: "skipped" }).eq("id", task.id);
      onUpdate?.();
    } finally {
      setLoading(null);
    }
  }

  if (!tasks.length) {
    return (
      <div className="rounded-xl border border-surface-3 bg-surface-1 p-6">
        <h3 className="font-semibold text-text-primary mb-2">Onboarding Tasks</h3>
        <p className="text-sm text-text-dim">No onboarding tasks created yet.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-surface-3 bg-surface-1 p-6 space-y-4">
      {/* Header + Progress */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-text-primary">Onboarding Tasks</h3>
        <span className="text-sm text-text-secondary">{completed}/{total} complete</span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            pct === 100 ? "bg-green-400" : "bg-accent",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Task List */}
      <div className="space-y-2">
        {tasks.map((task) => {
          const isOverdue = task.status === "pending" && new Date(task.due_date) < new Date();
          const status = isOverdue ? "overdue" : task.status;
          const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
          const isLoading = loading === task.id;

          return (
            <div
              key={task.id}
              className={cn(
                "flex items-start gap-3 p-3 rounded-lg border transition-colors",
                task.status === "completed"
                  ? "bg-green-500/5 border-green-500/20 opacity-60"
                  : isOverdue
                  ? "bg-red-500/5 border-red-500/20"
                  : "bg-surface-2 border-surface-3",
              )}
            >
              {/* Status icon */}
              <div className={cn("mt-0.5 flex-shrink-0", config.color)}>
                {config.icon}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className={cn(
                    "text-sm font-medium",
                    task.status === "completed" ? "line-through text-text-dim" : "text-text-primary",
                  )}>
                    Day {task.day_number} — {task.title}
                  </p>
                  <span className={cn("text-xs flex-shrink-0", config.color)}>
                    {config.label}
                  </span>
                </div>
                {task.description && (
                  <p className="text-xs text-text-dim mt-0.5">{task.description}</p>
                )}
                <p className="text-xs text-text-dim mt-1">
                  Due {formatDate(task.due_date)}
                </p>
                {task.notes && (
                  <p className="text-xs text-text-secondary mt-1 italic">"{task.notes}"</p>
                )}
              </div>

              {/* Actions */}
              {task.status !== "completed" && task.status !== "skipped" && (
                <div className="flex gap-1 flex-shrink-0">
                  <button
                    onClick={() => markDone(task)}
                    disabled={isLoading}
                    className="px-2 py-1 rounded text-xs bg-accent/15 text-accent hover:bg-accent/25 transition-colors disabled:opacity-50"
                  >
                    {isLoading ? "…" : "Done"}
                  </button>
                  <button
                    onClick={() => markSkipped(task)}
                    disabled={isLoading}
                    className="px-2 py-1 rounded text-xs bg-surface-3 text-text-dim hover:text-text-secondary transition-colors disabled:opacity-50"
                  >
                    Skip
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
