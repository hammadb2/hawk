"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { scansApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const LINES = [
  "Resolving DNS...",
  "Checking SPF, DMARC, DKIM...",
  "Probing SSL/TLS...",
  "Scanning ports...",
  "Fetching security headers...",
  "Enumerating subdomains...",
  "Computing grade...",
  "Done.",
];

export default function GatePage() {
  const { user, token } = useAuth();
  const [domain, setDomain] = useState("");
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<{ scan_id: string; score?: number; grade?: string; domain: string } | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [showLeadModal, setShowLeadModal] = useState(false);
  const [lineIndex, setLineIndex] = useState(0);

  const startScan = async () => {
    const d = domain.trim().toLowerCase().replace(/^https?:\/\//, "").split("/")[0].replace(/^www\./, "");
    if (!d) return;
    setScanning(true);
    setScanResult(null);
    setScanError(null);
    setLineIndex(0);
    const interval = setInterval(() => {
      setLineIndex((i) => Math.min(i + 1, LINES.length - 1));
    }, 600);
    try {
      if (token) {
        const res = await scansApi.start({ domain: d }, token);
        setScanResult({ scan_id: res.scan_id, score: res.score, grade: res.grade, domain: res.domain });
      } else {
        const res = await scansApi.startPublic({ domain: d });
        setScanResult({ scan_id: "", score: res.score, grade: res.grade, domain: res.domain });
      }
      setShowLeadModal(true);
    } catch (e) {
      setScanResult(null);
      setScanError(e instanceof Error ? e.message : "Scan failed. Try again or sign up to run from your dashboard.");
      setShowLeadModal(true);
    } finally {
      clearInterval(interval);
      setScanning(false);
    }
  };

  if (user) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center max-w-lg"
        >
          <h1 className="text-2xl font-extrabold text-text-primary mb-2">You’re signed in</h1>
          <p className="text-text-secondary mb-6">Go to your dashboard to run scans and view findings.</p>
          <Link href="/dashboard">
            <Button size="lg">Open dashboard</Button>
          </Link>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-surface-3 px-6 py-4 flex items-center justify-between">
        <Link href="/">
          <img src="/hawk-logo.png" alt="HAWK" className="h-12 w-auto" />
        </Link>
        <div className="flex gap-3">
          <Link href="/login">
            <Button variant="ghost">Log in</Button>
          </Link>
          <Link href="/login?register=1">
            <Button>Sign up</Button>
          </Link>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-6 py-16">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center max-w-2xl"
        >
          <h1 className="text-4xl md:text-5xl font-extrabold text-text-primary tracking-tight mb-4">
            See your external attack surface
          </h1>
          <p className="text-lg text-text-secondary mb-10">
            One domain scan. DNS, SSL, headers, and open ports — in plain English. Built for Canadian SMBs.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto mb-12">
            <Input
              placeholder="yourcompany.com"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && startScan()}
              className="flex-1"
              disabled={scanning}
            />
            <Button onClick={startScan} disabled={scanning || !domain.trim()} className="sm:w-auto">
              {scanning ? "Scanning…" : "Scan"}
            </Button>
          </div>

          <AnimatePresence>
            {scanning && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="rounded-xl border border-surface-3 bg-surface-1 p-4 text-left font-mono text-sm max-w-md mx-auto"
              >
                <div className="text-text-dim mb-2">$ hawk scan {domain || "domain"}</div>
                {LINES.slice(0, lineIndex + 1).map((line, i) => (
                  <motion.div
                    key={line}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-green/90"
                  >
                    {line}
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-16 flex flex-wrap justify-center gap-8 text-text-dim text-sm">
            <span>PIPEDA & Bill C-26 aware</span>
            <span>No intrusive scanning</span>
            <span>Canadian data</span>
          </div>
        </motion.div>
      </main>

      <AnimatePresence>
        {showLeadModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50"
            onClick={() => setShowLeadModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <Card className="w-full max-w-md">
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle>
                    {scanResult?.grade ? `Grade: ${scanResult.grade} (${scanResult.score}/100)` : "Scan complete"}
                  </CardTitle>
                  <button
                    type="button"
                    onClick={() => setShowLeadModal(false)}
                    className="text-text-dim hover:text-text-primary"
                    aria-label="Close"
                  >
                    ×
                  </button>
                </CardHeader>
                <CardContent>
                  {scanError ? (
                    <>
                      <p className="text-red mb-4">{scanError}</p>
                      <Link href={`/onboarding${scanResult?.domain ? `?domain=${encodeURIComponent(scanResult.domain)}` : ""}`}>
                        <Button className="w-full">Create free account</Button>
                      </Link>
                      <Button variant="ghost" className="w-full mt-2" onClick={() => setShowLeadModal(false)}>
                        Close
                      </Button>
                    </>
                  ) : scanResult?.scan_id || scanResult?.domain ? (
                    <>
                      <p className="text-text-secondary mb-4">
                        {scanResult.grade != null ? (
                          <>We scanned <strong className="text-text-primary">{scanResult.domain}</strong> — Grade {scanResult.grade} ({scanResult.score}/100). Sign up to save results and get compliance-ready reports.</>
                        ) : (
                          <>We’re ready to scan <strong className="text-text-primary">{scanResult.domain}</strong>. Sign up to run the scan, save results, and get compliance-ready reports.</>
                        )}
                      </p>
                      <Link href={`/onboarding${scanResult?.domain ? `?domain=${encodeURIComponent(scanResult.domain)}` : ""}`}>
                        <Button className="w-full">Create free account</Button>
                      </Link>
                      <Link href="/login" className="block mt-2">
                        <Button variant="ghost" className="w-full">I already have an account</Button>
                      </Link>
                    </>
                  ) : (
                    <>
                      <p className="text-text-secondary mb-4">The scan couldn’t complete. You can sign up and try again from your dashboard.</p>
                      <Link href={`/onboarding${scanResult?.domain ? `?domain=${encodeURIComponent(scanResult.domain)}` : ""}`}>
                        <Button className="w-full">Create free account</Button>
                      </Link>
                    </>
                  )}
                  {!scanError && (
                    <Button variant="ghost" className="w-full mt-2" onClick={() => setShowLeadModal(false)}>
                      Maybe later
                    </Button>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
