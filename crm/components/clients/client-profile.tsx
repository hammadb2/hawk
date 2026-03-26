"use client";

import { useState } from "react";
import { TrendingUp, AlertTriangle, CreditCard, FileText, Shield, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/ui/stat-card";
import { Button } from "@/components/ui/button";
import { formatCurrency, formatDate, churnRiskColor, cn } from "@/lib/utils";
import { clientsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import type { Client } from "@/types/crm";

interface ClientProfileProps {
  client: Client;
}

export function ClientProfile({ client }: ClientProfileProps) {
  const [generating, setGenerating] = useState(false);

  const daysAsClient = Math.floor(
    (Date.now() - new Date(client.close_date).getTime()) / (1000 * 60 * 60 * 24)
  );

  const handleGenerateReport = async () => {
    setGenerating(true);
    try {
      const result = await clientsApi.generateReport(client.id);
      if (result.success) {
        toast({ title: "Report generated and sent", variant: "success" });
      } else {
        toast({ title: result.error || "Failed to generate report", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Monthly Revenue"
          value={formatCurrency(client.mrr)}
          subValue={`${client.plan} plan`}
          accent
        />
        <StatCard
          label="Days as Client"
          value={daysAsClient.toString()}
          subValue={`Since ${formatDate(client.close_date)}`}
        />
        <div className="rounded-xl border border-border bg-surface-1 p-4">
          <p className="text-xs font-medium text-text-dim mb-1">Churn Risk</p>
          <span className={cn("text-sm font-semibold px-2 py-0.5 rounded-md capitalize", churnRiskColor(client.churn_risk_score))}>
            {client.churn_risk_score}
          </span>
        </div>
        <div className="rounded-xl border border-border bg-surface-1 p-4">
          <p className="text-xs font-medium text-text-dim mb-1">NPS Score</p>
          <p className={cn(
            "text-2xl font-bold",
            client.nps_latest === null ? "text-text-dim" :
            client.nps_latest >= 9 ? "text-green" :
            client.nps_latest >= 7 ? "text-yellow" : "text-red"
          )}>
            {client.nps_latest ?? "—"}
          </p>
        </div>
      </div>

      {/* Upsell flags */}
      {daysAsClient >= 60 && client.plan === "starter" && (
        <div className="flex items-center gap-3 p-3 rounded-xl border border-accent/30 bg-accent/5">
          <TrendingUp className="w-4 h-4 text-accent-light flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium text-text-primary">Shield upgrade opportunity</p>
            <p className="text-xs text-text-dim">Client has been on Starter for {daysAsClient} days — consider Shield upgrade</p>
          </div>
          <Badge variant="default" className="flex-shrink-0">Upsell</Badge>
        </div>
      )}

      {daysAsClient >= 90 && client.plan !== "enterprise" && (
        <div className="flex items-center gap-3 p-3 rounded-xl border border-yellow/30 bg-yellow/5">
          <TrendingUp className="w-4 h-4 text-yellow flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium text-text-primary">Enterprise upgrade opportunity</p>
            <p className="text-xs text-text-dim">Client has been active for {daysAsClient} days</p>
          </div>
          <Badge variant="warning" className="flex-shrink-0">Upsell</Badge>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Billing status */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="w-4 h-4 text-blue" />
              Billing Status
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-secondary">Status</span>
              <Badge
                variant={
                  client.status === "active" ? "success" :
                  client.status === "past_due" ? "warning" : "destructive"
                }
              >
                {client.status.replace("_", " ")}
              </Badge>
            </div>
            {client.stripe_customer_id && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">Stripe ID</span>
                <span className="text-xs font-mono text-text-dim">{client.stripe_customer_id}</span>
              </div>
            )}
            {client.clawback_deadline && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">Clawback Deadline</span>
                <span className="text-xs text-text-dim">{formatDate(client.clawback_deadline)}</span>
              </div>
            )}
            {client.last_login_at && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">Last Login</span>
                <span className="text-xs text-text-dim">{formatDate(client.last_login_at)}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Monthly report */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-accent-light" />
              Monthly Report
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-text-secondary mb-3">
              Generate and send the monthly security report to this client.
            </p>
            <Button
              onClick={handleGenerateReport}
              disabled={generating}
              variant="secondary"
              size="sm"
              className="gap-1.5"
            >
              {generating ? (
                <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Generating...</>
              ) : (
                <><FileText className="w-3.5 h-3.5" /> Generate & Send Report</>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
