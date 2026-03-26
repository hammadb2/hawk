"use client";

import { useState, useEffect } from "react";
import { Bot, Mail, Reply, Eye, UserPlus, TrendingUp, Globe, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/ui/stat-card";
import { Spinner } from "@/components/ui/spinner";
import { charlotteApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { CharlotteStats, SendingDomain, SequencePerformance } from "@/types/crm";

export function CharlotteModule() {
  const [stats, setStats] = useState<CharlotteStats | null>(null);
  const [domains, setDomains] = useState<SendingDomain[]>([]);
  const [sequences, setSequences] = useState<SequencePerformance[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [statsRes, domainsRes, seqRes] = await Promise.all([
          charlotteApi.stats(),
          charlotteApi.domains(),
          charlotteApi.sequences(),
        ]);

        if (statsRes.success && statsRes.data) setStats(statsRes.data);
        if (domainsRes.success && domainsRes.data) setDomains(domainsRes.data);
        if (seqRes.success && seqRes.data) setSequences(seqRes.data);
      } catch {
        toast({ title: "Failed to load Charlotte data", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  // Mock data for display
  const mockStats: CharlotteStats = stats ?? {
    sent_today: 248,
    opened_today: 104,
    replied_today: 20,
    positive_replies: 8,
    prospects_created: 12,
    closes_attributed: 3,
    last_ping: new Date(Date.now() - 120000).toISOString(),
    status: "healthy",
  };

  const mockDomains: SendingDomain[] = domains.length > 0 ? domains : [
    { id: "d1", domain: "outreach.hawk.ca", warmup_status: "active", daily_limit: 100, bounce_rate: 1.2, spam_rate: 0.3, delivery_rate_7d: 97.8 },
    { id: "d2", domain: "campaigns.hawk.ca", warmup_status: "warming", daily_limit: 50, bounce_rate: 0.8, spam_rate: 0.1, delivery_rate_7d: 99.1 },
  ];

  const mockSequences: SequencePerformance[] = sequences.length > 0 ? sequences : [
    { sequence_id: "s1", name: "Cold Outreach", step: 1, send_count: 850, open_rate: 38.2, click_rate: 4.1, reply_rate: 8.8 },
    { sequence_id: "s2", name: "Cold Outreach", step: 2, send_count: 620, open_rate: 31.5, click_rate: 2.8, reply_rate: 6.1 },
    { sequence_id: "s3", name: "Cold Outreach", step: 3, send_count: 410, open_rate: 24.4, click_rate: 1.9, reply_rate: 4.4 },
  ];

  const statusColor = mockStats.status === "healthy" ? "bg-green" : mockStats.status === "degraded" ? "bg-yellow" : "bg-red";

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
            <span className={cn(
              "text-xs font-medium",
              mockStats.status === "healthy" ? "text-green" :
              mockStats.status === "degraded" ? "text-yellow" : "text-red"
            )}>
              {mockStats.status === "healthy" ? "Operational" : mockStats.status === "degraded" ? "Degraded" : "Down"}
            </span>
          </h1>
          <p className="text-sm text-text-secondary">AI-powered outreach agent</p>
        </div>
      </div>

      {/* Today's stats */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard label="Sent Today" value={mockStats.sent_today.toString()} />
        <StatCard label="Opened" value={mockStats.opened_today.toString()} subValue={`${Math.round((mockStats.opened_today / mockStats.sent_today) * 100)}%`} />
        <StatCard label="Replied" value={mockStats.replied_today.toString()} subValue={`${Math.round((mockStats.replied_today / mockStats.sent_today) * 100)}%`} />
        <StatCard label="Positive" value={mockStats.positive_replies.toString()} accent />
        <StatCard label="Prospects Created" value={mockStats.prospects_created.toString()} />
        <StatCard label="Closes Attributed" value={mockStats.closes_attributed.toString()} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Sending domain health */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-blue" />
              Sending Domain Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {mockDomains.map((domain) => (
                <div key={domain.id} className="rounded-lg border border-border bg-surface-2 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-text-primary">{domain.domain}</span>
                    <Badge
                      variant={
                        domain.warmup_status === "active" ? "success" :
                        domain.warmup_status === "warming" ? "warning" :
                        domain.warmup_status === "paused" ? "secondary" : "destructive"
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
          </CardContent>
        </Card>

        {/* Sequence performance */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-accent-light" />
              Sequence Performance
            </CardTitle>
          </CardHeader>
          <CardContent>
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
                {mockSequences.map((seq) => (
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
