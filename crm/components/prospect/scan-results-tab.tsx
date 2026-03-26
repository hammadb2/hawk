"use client";

import { useState, useEffect } from "react";
import { Shield, AlertTriangle, Info, ChevronDown, ChevronUp, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import { prospectsApi, scansApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { useCRMStore } from "@/store/crm-store";
import { formatDateTime, cn } from "@/lib/utils";
import type { ScanResult, ScanFinding } from "@/types/crm";

const SEVERITY_CONFIG = {
  critical: { label: "Critical", color: "text-red", bg: "bg-red/10 border-red/25", icon: AlertTriangle },
  high: { label: "High", color: "text-orange", bg: "bg-orange/10 border-orange/25", icon: AlertTriangle },
  medium: { label: "Medium", color: "text-yellow", bg: "bg-yellow/10 border-yellow/25", icon: AlertTriangle },
  low: { label: "Low", color: "text-blue", bg: "bg-blue/10 border-blue/25", icon: Info },
  info: { label: "Info", color: "text-text-secondary", bg: "bg-surface-3 border-border", icon: Info },
};

interface ScanResultsTabProps {
  prospectId: string;
}

export function ScanResultsTab({ prospectId }: ScanResultsTabProps) {
  const { updateProspect } = useCRMStore();
  const [scans, setScans] = useState<ScanResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [expandedFindings, setExpandedFindings] = useState<Set<string>>(new Set());

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const result = await scansApi.getForProspect(prospectId);
      if (result.success && result.data) {
        setScans(result.data);
      }
      setLoading(false);
    };
    load();
  }, [prospectId]);

  const handleRunScan = async () => {
    setScanning(true);
    try {
      const result = await prospectsApi.runScan(prospectId);
      if (result.success && result.data) {
        setScans((prev) => [result.data!, ...prev]);
        updateProspect(prospectId, { hawk_score: result.data.hawk_score ?? undefined });
        toast({ title: "Scan completed", variant: "success" });
      } else {
        toast({ title: result.error || "Scan failed", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error running scan", variant: "destructive" });
    } finally {
      setScanning(false);
    }
  };

  const toggleFinding = (id: string) => {
    setExpandedFindings((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const latestScan = scans[0];
  const previousScan = scans[1];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-secondary">HAWK Scan Results</h3>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRunScan}
          disabled={scanning}
          className="gap-1.5"
        >
          {scanning ? (
            <><Spinner size="sm" /> Scanning...</>
          ) : (
            <><RefreshCw className="w-3.5 h-3.5" /> Run New Scan</>
          )}
        </Button>
      </div>

      {scanning && (
        <div className="flex items-center gap-3 p-4 rounded-xl border border-accent/30 bg-accent/5">
          <Spinner size="sm" />
          <div>
            <p className="text-sm font-medium text-text-primary">Scanning in progress...</p>
            <p className="text-xs text-text-dim">This may take 30–90 seconds</p>
          </div>
        </div>
      )}

      {latestScan ? (
        <>
          {/* Score display */}
          <div className="flex items-center gap-4 p-4 rounded-xl border border-border bg-surface-2">
            <HawkScoreRing score={latestScan.hawk_score} size="lg" showLabel />
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <p className="text-sm font-semibold text-text-primary">
                  {latestScan.hawk_score !== null ? "Risk Score" : "No score"}
                </p>
                {previousScan?.hawk_score !== null && latestScan.hawk_score !== null && (
                  <Badge
                    variant={latestScan.hawk_score > (previousScan?.hawk_score ?? 0) ? "destructive" : "success"}
                    className="text-2xs"
                  >
                    {latestScan.hawk_score > (previousScan?.hawk_score ?? 0) ? "+" : ""}
                    {latestScan.hawk_score - (previousScan?.hawk_score ?? 0)} vs last
                  </Badge>
                )}
              </div>
              <p className="text-xs text-text-dim">
                Scanned {formatDateTime(latestScan.created_at)}
                {latestScan.triggered_by_user && ` by ${latestScan.triggered_by_user.name}`}
              </p>
            </div>
          </div>

          {/* Findings */}
          {latestScan.findings.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-text-dim uppercase tracking-wide">
                {latestScan.findings.length} Finding{latestScan.findings.length !== 1 ? "s" : ""}
              </p>
              {latestScan.findings.map((finding: ScanFinding) => {
                const config = SEVERITY_CONFIG[finding.severity] ?? SEVERITY_CONFIG.info;
                const ConfigIcon = config.icon;
                const expanded = expandedFindings.has(finding.id);

                return (
                  <div
                    key={finding.id}
                    className={cn("rounded-lg border p-3 cursor-pointer transition-all", config.bg)}
                    onClick={() => toggleFinding(finding.id)}
                  >
                    <div className="flex items-start gap-2.5">
                      <ConfigIcon className={cn("w-4 h-4 mt-0.5 flex-shrink-0", config.color)} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-sm font-medium text-text-primary">{finding.title}</span>
                          <Badge variant="secondary" className={cn("text-2xs ml-auto", config.color)}>
                            {config.label}
                          </Badge>
                        </div>
                        <p className="text-xs text-text-secondary">{finding.description}</p>
                        {expanded && finding.remediation && (
                          <div className="mt-2 pt-2 border-t border-border/50">
                            <p className="text-xs font-medium text-text-secondary mb-1">Remediation</p>
                            <p className="text-xs text-text-dim">{finding.remediation}</p>
                          </div>
                        )}
                      </div>
                      {finding.remediation && (
                        <div className="flex-shrink-0 text-text-dim">
                          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-green/5 border border-green/20">
              <Shield className="w-4 h-4 text-green" />
              <p className="text-sm text-green">No findings — clean scan</p>
            </div>
          )}
        </>
      ) : (
        <EmptyState
          icon={Shield}
          title="No scans yet"
          description="Run a HAWK scan to see security findings for this domain."
          action={{ label: "Run Scan", onClick: handleRunScan }}
        />
      )}
    </div>
  );
}
