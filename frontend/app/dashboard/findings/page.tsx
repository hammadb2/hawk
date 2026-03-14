"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { findingsApi, scansApi, type Finding } from "@/lib/api";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "border-red/50 bg-red/10 text-red",
  warning: "border-orange/50 bg-orange/10 text-orange",
  info: "border-blue/50 bg-blue/10 text-blue",
  ok: "border-green/50 bg-green/10 text-green",
};

export default function DashboardFindingsPage() {
  const searchParams = useSearchParams();
  const scanIdFromUrl = searchParams.get("scan");
  const { token } = useAuth();
  const [scans, setScans] = useState<{ id: string; score: number | null; grade: string | null; started_at: string | null }[]>([]);
  const [scanIdInput, setScanIdInput] = useState(scanIdFromUrl || "");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [score, setScore] = useState<number | null>(null);
  const [grade, setGrade] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    if (!token) return;
    scansApi.list(token).then((r) => setScans(r.scans)).catch(() => {});
  }, [token]);

  const loadFindings = (id: string) => {
    if (!token || !id) return;
    setLoading(true);
    findingsApi
      .list(id, token)
      .then((r) => {
        setFindings(r.findings);
        setScore(r.score ?? null);
        setGrade(r.grade ?? null);
        setScanIdInput(id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (scanIdFromUrl && token) loadFindings(scanIdFromUrl);
  }, [scanIdFromUrl, token]);

  const filtered = filter === "all" ? findings : findings.filter((f) => f.severity === filter);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Findings</h1>
        <p className="text-text-secondary mt-1">View and filter findings from a scan.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Select scan</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
            <div className="flex gap-2 flex-wrap items-center">
              <select
                className="flex h-10 rounded-lg border border-surface-3 bg-surface-1 px-3 py-2 text-sm text-text-primary min-w-[200px]"
                value={scanIdInput}
                onChange={(e) => {
                  const id = e.target.value;
                  if (id) loadFindings(id);
                  setScanIdInput(id);
                }}
              >
                <option value="">Choose a scan…</option>
                {scans.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id.slice(0, 8)}… — {s.grade ?? "—"} ({s.score ?? "—"}) — {s.started_at ? new Date(s.started_at).toLocaleString() : ""}
                  </option>
                ))}
              </select>
              <span className="text-text-dim text-sm">or</span>
              <input
                className="flex h-10 rounded-lg border border-surface-3 bg-surface-1 px-3 py-2 text-sm text-text-primary w-48"
                placeholder="Paste scan ID"
                value={scanIdInput}
                onChange={(e) => setScanIdInput(e.target.value)}
              />
              <Button onClick={() => loadFindings(scanIdInput)} disabled={loading || !scanIdInput.trim()}>
                Load
              </Button>
            </div>
            {grade != null && (
              <p className="mt-2 text-sm text-text-secondary">
                Grade: <span className={cn("font-semibold", SEVERITY_STYLES[grade.toLowerCase()] || "")}>{grade}</span>
                {score != null && ` (${score}/100)`}
              </p>
            )}
          </CardContent>
      </Card>

      <div className="flex gap-2 flex-wrap">
        {["all", "critical", "warning", "info", "ok"].map((s) => (
          <Button
            key={s}
            variant={filter === s ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(s)}
          >
            {s}
          </Button>
        ))}
      </div>

      <div className="space-y-3">
        {loading && <p className="text-text-dim">Loading…</p>}
        {!loading && filtered.length === 0 && <p className="text-text-dim">No findings. Load a scan or run one first.</p>}
        {!loading && filtered.map((f) => (
          <motion.div
            key={f.id}
            layout
            className={cn(
              "rounded-lg border p-4",
              SEVERITY_STYLES[f.severity] || "border-surface-3 bg-surface-1"
            )}
          >
            <button
              type="button"
              className="w-full text-left flex items-center justify-between"
              onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}
            >
              <span className="font-medium">{f.title}</span>
              <span className="text-sm opacity-80">{f.severity}</span>
            </button>
            {expandedId === f.id && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="mt-3 pt-3 border-t border-surface-3 space-y-2 text-sm text-text-secondary"
              >
                <p>{f.description}</p>
                <p className="font-mono text-xs text-text-dim">{f.technical_detail}</p>
                <p><span className="text-text-primary">Remediation:</span> {f.remediation}</p>
                {f.compliance?.length > 0 && (
                  <p className="text-accent">Compliance: {f.compliance.join(", ")}</p>
                )}
              </motion.div>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}
