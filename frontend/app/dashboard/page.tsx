"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { scansApi, domainsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const GRADE_COLORS: Record<string, string> = {
  A: "text-green",
  B: "text-blue",
  C: "text-yellow",
  D: "text-orange",
  F: "text-red",
};

export default function DashboardOverviewPage() {
  const { token, user } = useAuth();
  const router = useRouter();
  const [scans, setScans] = useState<{ id: string; status: string; score: number | null; grade: string | null; started_at: string | null }[]>([]);
  const [criticalCount, setCriticalCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [scanDomain, setScanDomain] = useState("");
  const [accountDomain, setAccountDomain] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      scansApi.list(token).then((r) => {
        const list = r.scans.slice(0, 5);
        setScans(list);
        const latestId = list[0]?.id;
        if (latestId) {
          return scansApi.get(latestId, token).then((scan) => {
            try {
              const findings = JSON.parse(scan.findings_json || "[]");
              setCriticalCount(findings.filter((f: { severity?: string }) => f.severity === "critical").length);
            } catch {
              setCriticalCount(0);
            }
          });
        }
      }),
      domainsApi.list(token).then((r) => {
        const first = r.domains[0]?.domain ?? null;
        setAccountDomain(first);
        if (first) setScanDomain(first);
      }),
    ])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const runScan = async () => {
    if (!token) return;
    const d = scanDomain.trim().toLowerCase().replace(/^https?:\/\//, "").split("/")[0].replace(/^www\./, "");
    if (!d) return;
    setScanning(true);
    setScanError(null);
    try {
      const res = await scansApi.start({ domain: d }, token);
      router.push(`/dashboard/findings?scan=${res.scan_id}`);
    } catch (e) {
      setScanError(e instanceof Error ? e.message : "Scan failed. Please try again.");
      setScanning(false);
    }
  };

  const latest = scans[0];
  const planLabel =
    user?.plan === "starter"
      ? "Starter"
      : user?.plan === "pro"
        ? "Pro"
        : user?.plan === "agency"
          ? "Agency"
          : user?.plan
            ? String(user.plan).replace(/_/g, " ")
            : "—";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Overview</h1>
        <p className="text-text-secondary mt-1">Your attack surface at a glance.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-text-secondary">Current grade</CardTitle>
            </CardHeader>
            <CardContent>
              {latest?.grade != null ? (
                <span className={cn("text-3xl font-extrabold", GRADE_COLORS[latest.grade] || "text-text-primary")}>
                  {latest.grade}
                </span>
              ) : (
                <span className="text-3xl font-extrabold text-text-dim">—</span>
              )}
              {latest?.score != null && (
                <p className="text-xs text-text-dim mt-1">{latest.score}/100</p>
              )}
            </CardContent>
          </Card>
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-text-secondary">Scans</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-3xl font-extrabold text-text-primary">{loading ? "—" : scans.length}</span>
              <p className="text-xs text-text-dim mt-1">Recent (last 5)</p>
            </CardContent>
          </Card>
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-text-secondary">Critical findings</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-3xl font-extrabold text-red">{criticalCount}</span>
              <p className="text-xs text-text-dim mt-1">Needs attention</p>
            </CardContent>
          </Card>
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-text-secondary">Plan</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-lg font-semibold text-text-primary capitalize">{planLabel}</span>
              <p className="text-xs text-text-dim mt-1">Active plan</p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Quick scan</CardTitle>
            <CardDescription className="text-text-secondary">
              {accountDomain
                ? `Run a scan for ${accountDomain}.`
                : "Enter a domain and run a scan now, or add a domain in Domains to scan on a schedule."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {accountDomain ? (
              <Button onClick={runScan} disabled={scanning}>
                {scanning ? "Scanning…" : "Run Scan"}
              </Button>
            ) : (
              <div className="flex gap-2">
                <Input
                  placeholder="yourcompany.com"
                  value={scanDomain}
                  onChange={(e) => setScanDomain(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runScan()}
                  disabled={scanning}
                  className="flex-1"
                />
                <Button onClick={runScan} disabled={scanning || !scanDomain.trim()}>
                  {scanning ? "Scanning…" : "Run Scan"}
                </Button>
              </div>
            )}
            {scanError && <p className="text-red text-sm mt-2">{scanError}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription className="text-text-secondary">
              Latest scan results.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-text-dim text-sm">Loading…</p>
            ) : scans.length === 0 ? (
              <p className="text-text-dim text-sm">No scans yet. Run a scan from the home page.</p>
            ) : (
              <ul className="space-y-2">
                {scans.map((s) => (
                  <li key={s.id} className="flex items-center justify-between text-sm">
                    <Link href={`/dashboard/findings?scan=${s.id}`} className="text-accent hover:underline">
                      Scan {s.id.slice(0, 8)}…
                    </Link>
                    <span className={cn("font-medium", GRADE_COLORS[s.grade || ""] || "text-text-secondary")}>
                      {s.grade ?? "—"} {s.score != null ? `(${s.score})` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Breach Check</CardTitle>
            <CardDescription className="text-text-secondary">
              Check if staff email addresses appear in known data breaches via HaveIBeenPwned.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/dashboard/breach">
              <Button variant="secondary">Run breach check</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
