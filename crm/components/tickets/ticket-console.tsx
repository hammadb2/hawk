"use client";

import { useState, useEffect } from "react";
import { LifeBuoy } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { ticketsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { formatDateTime, cn } from "@/lib/utils";
import type { Ticket, TicketStatus } from "@/types/crm";

const STATUS_CONFIG: Record<TicketStatus, { label: string; variant: "secondary" | "info" | "success" | "warning" | "destructive" }> = {
  received: { label: "Received", variant: "secondary" },
  in_progress: { label: "In Progress", variant: "info" },
  resolved: { label: "Resolved", variant: "success" },
  duplicate: { label: "Duplicate", variant: "warning" },
  monitoring: { label: "Monitoring", variant: "warning" },
};

const SEVERITY_LABELS: Record<number, string> = {
  1: "P1 Critical",
  2: "P2 High",
  3: "P3 Medium",
  4: "P4 Low",
  5: "P5 Info",
};

export function TicketConsole() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<TicketStatus | "all">("all");
  const [stats, setStats] = useState<{
    avg_resolution_hours: number;
    auto_resolve_pct: number;
    user_error_pct: number;
    open_over_4h: number;
  } | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [listRes, statsRes] = await Promise.all([ticketsApi.list(), ticketsApi.stats()]);
        if (listRes.success && listRes.data) {
          setTickets(listRes.data);
        } else {
          setTickets([]);
          toast({ title: "Failed to load tickets", variant: "destructive" });
        }
        if (statsRes.success && statsRes.data) {
          setStats(statsRes.data);
        }
      } catch {
        setTickets([]);
        toast({ title: "Failed to load tickets", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const handleUpdateStatus = async (id: string, status: TicketStatus) => {
    try {
      const result = await ticketsApi.updateStatus(id, status);
      if (result.success && result.data) {
        setTickets((prev) => prev.map((t) => (t.id === id ? { ...t, ...result.data } : t)));
        toast({ title: "Ticket status updated", variant: "success" });
      } else {
        toast({ title: result.error || "Failed to update ticket", variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to update ticket", variant: "destructive" });
    }
  };

  const filtered = statusFilter === "all"
    ? tickets
    : tickets.filter((t) => t.status === statusFilter);

  const openCount = tickets.filter((t) => t.status === "received" || t.status === "in_progress").length;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-text-primary flex items-center gap-2">
          <LifeBuoy className="w-5 h-5 text-blue" />
          Support Tickets
          {openCount > 0 && (
            <Badge variant="info">{openCount} open</Badge>
          )}
        </h1>
        <p className="text-sm text-text-secondary mt-0.5">Self-healing console and support triage</p>
      </div>

      {/* Resolution stats — API when available; placeholders otherwise */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Open Tickets" value={openCount.toString()} />
        <StatCard
          label="Avg resolution"
          value={stats != null ? `${stats.avg_resolution_hours.toFixed(1)}h` : "—"}
          subValue={stats ? undefined : "API offline"}
        />
        <StatCard
          label="Auto-resolved"
          value={stats != null ? `${Math.round(stats.auto_resolve_pct)}%` : "—"}
        />
        <StatCard
          label="Open &gt;4h"
          value={stats != null ? String(stats.open_over_4h) : "—"}
        />
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        {(["all", "received", "in_progress", "resolved", "duplicate", "monitoring"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
              statusFilter === s
                ? "bg-accent/15 border-accent/30 text-accent-light"
                : "border-border text-text-dim hover:text-text-secondary hover:bg-surface-2"
            )}
          >
            {s === "all" ? "All" : STATUS_CONFIG[s as TicketStatus]?.label ?? s}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={LifeBuoy}
          title="No tickets found"
          description="All clear!"
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((ticket) => (
            <div
              key={ticket.id}
              className={cn(
                "rounded-xl border p-4",
                ticket.severity === 1 ? "border-red/30 bg-red/5" :
                ticket.severity === 2 ? "border-orange/30 bg-orange/5" :
                "border-border bg-surface-1"
              )}
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge
                      variant={
                        ticket.severity === 1 ? "destructive" :
                        ticket.severity === 2 ? "orange" :
                        "secondary"
                      }
                      className="text-2xs"
                    >
                      {ticket.severity ? SEVERITY_LABELS[ticket.severity] : "Unknown"}
                    </Badge>
                    <Badge variant={STATUS_CONFIG[ticket.status]?.variant ?? "secondary"} className="text-2xs">
                      {STATUS_CONFIG[ticket.status]?.label ?? ticket.status}
                    </Badge>
                    <span className="text-2xs text-text-dim capitalize ml-auto">
                      {ticket.channel.replace("_", " ")}
                    </span>
                  </div>
                  <p className="text-sm text-text-primary mb-1">{ticket.raw_text}</p>
                  {ticket.triage_diagnosis && (
                    <p className="text-xs text-text-secondary bg-surface-2 rounded p-2 mt-1">
                      <span className="font-medium text-text-dim">Diagnosis: </span>
                      {ticket.triage_diagnosis}
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-2xs text-text-dim">{formatDateTime(ticket.created_at)}</span>
                    {ticket.pr_url && (
                      <a
                        href={ticket.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-2xs text-accent-light hover:text-accent transition-colors"
                      >
                        View PR →
                      </a>
                    )}
                  </div>
                </div>

                {!["resolved", "duplicate"].includes(ticket.status) && (
                  <div className="flex flex-col gap-1.5 flex-shrink-0 min-w-[5.5rem]">
                    {ticket.status === "received" && (
                      <Button
                        variant="secondary"
                        size="sm"
                        className="h-7 text-2xs"
                        onClick={() => void handleUpdateStatus(ticket.id, "in_progress")}
                      >
                        Start
                      </Button>
                    )}
                    <Button
                      variant="success"
                      size="sm"
                      className="h-7 text-2xs"
                      onClick={() => void handleUpdateStatus(ticket.id, "resolved")}
                    >
                      Resolve
                    </Button>
                    <Button
                      variant="warning"
                      size="sm"
                      className="h-7 text-2xs"
                      onClick={() => void handleUpdateStatus(ticket.id, "duplicate")}
                    >
                      Duplicate
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="h-7 text-2xs"
                      onClick={() => void handleUpdateStatus(ticket.id, "monitoring")}
                    >
                      Monitor
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
