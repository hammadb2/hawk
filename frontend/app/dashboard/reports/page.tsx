"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { reportsApi, scansApi } from "@/lib/api";
import type { ScanListItem } from "@/lib/api";

export default function DashboardReportsPage() {
  const { token } = useAuth();
  const [reports, setReports] = useState<{ id: string; scan_id: string; domain: string; pdf_path: string | null; created_at: string | null }[]>([]);
  const [scans, setScans] = useState<ScanListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [scanId, setScanId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    Promise.all([
      reportsApi.list(token),
      scansApi.list(token),
    ])
      .then(([r, s]) => {
        setReports(r.reports);
        const completed = s.scans.filter((sc) => sc.status === "completed").slice(0, 20);
        setScans(completed);
        if (completed.length > 0) setScanId(completed[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const generate = async () => {
    if (!token || !scanId.trim()) return;
    setGenerating(true);
    setError("");
    try {
      await reportsApi.generate({ scan_id: scanId.trim(), sections: ["executive", "findings", "compliance"] }, token);
      const r = await reportsApi.list(token);
      setReports(r.reports);
    } catch (e) {
      setError(e instanceof Error ? e.message : "PDF generation failed. Please try again.");
    } finally {
      setGenerating(false);
    }
  };

  const downloadPdf = async (reportId: string, domain: string) => {
    if (!token) return;
    try {
      const res = await fetch(reportsApi.pdfUrl(reportId), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Download failed");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `hawk-report-${domain}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Download failed");
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Reports</h1>
        <p className="text-text-secondary mt-1">Generate and download PDF security reports from your scans.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Generate PDF report</CardTitle>
        </CardHeader>
        <CardContent className="pt-0 space-y-3">
          {loading ? (
            <p className="text-text-dim text-sm">Loading scans…</p>
          ) : scans.length === 0 ? (
            <p className="text-text-dim text-sm">No completed scans found. Run a scan first.</p>
          ) : (
            <div className="flex gap-2 flex-wrap items-center">
              <select
                className="h-10 rounded-lg border border-surface-3 bg-surface-1 px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
                value={scanId}
                onChange={(e) => setScanId(e.target.value)}
              >
                {scans.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id.slice(0, 8)}… — Grade {s.grade ?? "?"} ({s.score ?? "?"}/100){s.started_at ? ` · ${new Date(s.started_at).toLocaleDateString()}` : ""}
                  </option>
                ))}
              </select>
              <Button onClick={generate} disabled={generating || !scanId.trim()}>
                {generating ? "Generating…" : "Generate PDF"}
              </Button>
            </div>
          )}
          {error && <p className="text-sm text-red">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your reports</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {loading ? (
            <p className="text-text-dim text-sm">Loading…</p>
          ) : reports.length === 0 ? (
            <p className="text-text-dim text-sm">No reports yet. Generate one above.</p>
          ) : (
            <ul className="divide-y divide-surface-3">
              {reports.map((r) => (
                <li key={r.id} className="flex items-center justify-between py-3 text-sm">
                  <div>
                    <span className="text-text-primary font-medium">{r.domain}</span>
                    <span className="text-text-dim ml-2">
                      {r.created_at ? new Date(r.created_at).toLocaleDateString() : ""}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => downloadPdf(r.id, r.domain)}
                    className="text-accent hover:text-accent-light transition-colors"
                  >
                    Download PDF
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
