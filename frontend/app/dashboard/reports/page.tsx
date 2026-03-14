"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { reportsApi } from "@/lib/api";

export default function DashboardReportsPage() {
  const { token } = useAuth();
  const [reports, setReports] = useState<{ id: string; scan_id: string; domain: string; pdf_path: string | null; created_at: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [scanId, setScanId] = useState("");

  useEffect(() => {
    if (!token) return;
    reportsApi
      .list(token)
      .then((r) => setReports(r.reports))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const generate = async () => {
    if (!token || !scanId.trim()) return;
    setGenerating(true);
    try {
      await reportsApi.generate({ scan_id: scanId.trim(), sections: ["executive", "findings", "compliance"] }, token);
      const r = await reportsApi.list(token);
      setReports(r.reports);
      setScanId("");
    } catch {
      // ignore
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Reports</h1>
        <p className="text-text-secondary mt-1">Generate and download PDF reports from a scan.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Generate report</CardTitle>
        </CardHeader>
        <CardContent className="pt-0 flex gap-2 flex-wrap items-center">
            <input
              className="flex h-10 rounded-lg border border-surface-3 bg-surface-1 px-3 py-2 text-sm text-text-primary w-64"
              placeholder="Scan ID"
              value={scanId}
              onChange={(e) => setScanId(e.target.value)}
            />
            <Button onClick={generate} disabled={generating || !scanId.trim()}>
              {generating ? "Generating…" : "Generate PDF"}
            </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your reports</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
            {loading ? (
              <p className="text-text-dim">Loading…</p>
            ) : reports.length === 0 ? (
              <p className="text-text-dim">No reports yet. Generate one above.</p>
            ) : (
              <ul className="space-y-2">
                {reports.map((r) => (
                  <li key={r.id} className="flex items-center justify-between text-sm">
                    <span>{r.domain} — {r.created_at ? new Date(r.created_at).toLocaleDateString() : ""}</span>
                    <button
                      type="button"
                      onClick={async () => {
                        if (!token) return;
                        const res = await fetch(reportsApi.pdfUrl(r.id), { headers: { Authorization: `Bearer ${token}` } });
                        const blob = await res.blob();
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `hawk-report-${r.domain}.pdf`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className="text-accent hover:underline"
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
