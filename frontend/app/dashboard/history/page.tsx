"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { scansApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const GRADE_COLORS: Record<string, string> = {
  A: "text-green",
  B: "text-blue",
  C: "text-yellow",
  D: "text-orange",
  F: "text-red",
};

export default function DashboardHistoryPage() {
  const { token } = useAuth();
  const [scans, setScans] = useState<{ id: string; status: string; score: number | null; grade: string | null; started_at: string | null; completed_at: string | null }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    scansApi
      .list(token)
      .then((r) => setScans(r.scans))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Scan history</h1>
        <p className="text-text-secondary mt-1">All past scans. Open one to view or compare findings.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Scans</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
            {loading ? (
              <p className="text-text-dim">Loading…</p>
            ) : scans.length === 0 ? (
              <p className="text-text-dim">No scans yet. Run a scan from the home page.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-text-secondary border-b border-surface-3">
                      <th className="pb-2 pr-4">Date</th>
                      <th className="pb-2 pr-4">Scan ID</th>
                      <th className="pb-2 pr-4">Status</th>
                      <th className="pb-2 pr-4">Grade</th>
                      <th className="pb-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {scans.map((s) => (
                      <tr key={s.id} className="border-b border-surface-3/50">
                        <td className="py-3 pr-4 text-text-secondary">
                          {s.started_at ? new Date(s.started_at).toLocaleString() : "—"}
                        </td>
                        <td className="py-3 pr-4 font-mono text-text-dim">{s.id.slice(0, 8)}…</td>
                        <td className="py-3 pr-4 capitalize">{s.status}</td>
                        <td className={cn("py-3 pr-4 font-semibold", GRADE_COLORS[s.grade || ""] || "text-text-primary")}>
                          {s.grade ?? "—"} {s.score != null ? `(${s.score})` : ""}
                        </td>
                        <td className="py-3">
                          <Link href={`/dashboard/findings?scan=${s.id}`}>
                            <Button variant="ghost" size="sm">View findings</Button>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
      </Card>
    </div>
  );
}
