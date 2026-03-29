"use client";

import { useState, useEffect } from "react";
import { Bot, Mail, Globe } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/ui/stat-card";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { charlotteApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { CharlotteStats, SendingDomain, SequencePerformance } from "@/types/crm";

export function CharlotteModule() {
  const [stats, setStats] = useState<CharlotteStats | null>(null);
  const [domains, setDomains] = useState<SendingDomain[]>([]);
  const [sequences, setSequences] = useState<SequencePerformance[]>([]);
  const [loading, setLoading] = useState(false);
  const [fatalError, setFatalError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setFatalError(null);
      try {
        const [statsRes, domainsRes, seqRes] = await Promise.all([
          charlotteApi.stats(),
          charlotteApi.domains(),
          charlotteApi.sequences(),
        ]);

        const statsOk = statsRes.success && statsRes.data;
        if (!statsOk) {
          setFatalError(statsRes.error ?? "Charlotte metrics could not be loaded. The outreach service may be down.");
          setStats(null);
        } else {
          setStats(statsRes.data);
        }

        if (domainsRes.success && domainsRes.data) {
          setDomains(domainsRes.data);
        } else {
          setDomains([]);
        }

        if (seqRes.success && seqRes.data) {
          setSequences(seqRes.data);
        } else {
          setSequences([]);
        }

        if (!statsOk) {
          toast({ title: "Charlotte unavailable", description: statsRes.error ?? undefined, variant: "destructive" });
        }
      } catch {
        setFatalError("Network error while loading Charlotte.");
        setStats(null);
        setDomains([]);
        setSequences([]);
        toast({ title: "Failed to load Charlotte data", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  if (fatalError || !stats) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <EmptyState
          icon={Bot}
          title="Charlotte data unavailable"
          description={fatalError ?? "We could not load live outreach stats. Do not rely on cached or demo numbers — verify the Charlotte API before acting."}
          className="mt-12"
        />
      </div>
    );
  }

  const statusColor = stats.status === "healthy" ? "bg-green" : stats.status === "degraded" ? "bg-yellow" : "bg-red";
  const openPct =
    stats.sent_today > 0 ? Math.round((stats.opened_today / stats.sent_today) * 100) : 0;
  const replyPct =
    stats.sent_today > 0 ? Math.round((stats.replied_today / stats.sent_today) * 100) : 0;

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-accent/20 border border-accent/40 flex items-center justify-center">
          <Bot className="w-5 h-5 text-accent-light" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-text-primary flex items-center gap-2">
            Charlotte
            <span className={cn("w-2 h-2 rounded-full realtime-dot", statusColor)} />
            <span
              className={cn(
                "text-xs font-medium",
                stats.status === "healthy"
                  ? "text-green"
                  : stats.status === "degraded"
                    ? "text-yellow"
                    : "text-red"
              )}
            >
              {stats.status === "healthy"
                ? "Operational"
                : stats.status === "degraded"
                  ? "Degraded"
                  : "Down"}
            </span>
          </h1>
          <p className="text-sm text-text-secondary">AI-powered outreach agent</p>
        </div>
      </div>

      {/* Today's stats */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard label="Sent Today" value={stats.sent_today.toString()} />
        <StatCard
          label="Opened"
          value={stats.opened_today.toString()}
          subValue={stats.sent_today > 0 ? `${openPct}%` : "—"}
        />
        <StatCard
          label="Replied"
          value={stats.replied_today.toString()}
          subValue={stats.sent_today > 0 ? `${replyPct}%` : "—"}
        />
        <StatCard label="Positive" value={stats.positive_replies.toString()} accent />
        <StatCard label="Prospects Created" value={stats.prospects_created.toString()} />
        <StatCard label="Closes Attributed" value={stats.closes_attributed.toString()} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-blue" />
              Sending Domain Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            {domains.length === 0 ? (
              <p className="text-xs text-text-dim text-center py-6">No sending domains returned from the API.</p>
            ) : (
              <div className="space-y-3">
                {domains.map((domain) => (
                  <div key={domain.id} className="rounded-lg border border-border bg-surface-2 p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-text-primary">{domain.domain}</span>
                      <Badge
                        variant={
                          domain.warmup_status === "active"
                            ? "success"
                            : domain.warmup_status === "warming"
                              ? "warning"
                              : domain.warmup_status === "paused"
                                ? "secondary"
                                : "destructive"
                        }
                        className="text-2xs capitalize"
                      >
                        {domain.warmup_status}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-center">
                      {[
                        { label: "Limit/day", value: domain.daily_limit },
                        { label: "Bounce %", value: `${domain.bounce_rate}%` },
                        { label: "Spam %", value: `${domain.spam_rate}%` },
                        { label: "Delivery 7d", value: `${domain.delivery_rate_7d}%` },
                      ].map(({ label, value }) => (
                        <div key={label}>
                          <p className="text-xs font-semibold text-text-primary">{value}</p>
                          <p className="text-2xs text-text-dim">{label}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-accent-light" />
              Sequence Performance
            </CardTitle>
          </CardHeader>
          <CardContent>
            {sequences.length === 0 ? (
              <p className="text-xs text-text-dim text-center py-6">No sequence data returned from the API.</p>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="text-left border-b border-border">
                    <th className="text-2xs font-medium text-text-dim pb-2">Sequence</th>
                    <th className="text-2xs font-medium text-text-dim pb-2 text-right">Sent</th>
                    <th className="text-2xs font-medium text-text-dim pb-2 text-right">Open%</th>
                    <th className="text-2xs font-medium text-text-dim pb-2 text-right">Reply%</th>
                  </tr>
                </thead>
                <tbody>
                  {sequences.map((seq) => (
                    <tr key={`${seq.sequence_id}-${seq.step}`} className="border-b border-border/50 last:border-0">
                      <td className="py-2">
                        <span className="text-xs text-text-primary">{seq.name}</span>
                        <span className="text-2xs text-text-dim ml-1">#{seq.step}</span>
                      </td>
                      <td className="py-2 text-right text-xs text-text-secondary">{seq.send_count}</td>
                      <td className="py-2 text-right text-xs text-blue">{seq.open_rate}%</td>
                      <td className="py-2 text-right text-xs text-green">{seq.reply_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
