"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { scansApi, marketingApi, type PublicScanResult } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const BRAND = "#22C55E";

function normalizeDomain(raw: string): string {
  let d = raw.trim().toLowerCase();
  if (d.startsWith("http")) d = d.split("//").pop()!.split("/")[0];
  if (d.startsWith("www.")) d = d.slice(4);
  return d;
}

function gradeStroke(grade: string | undefined): string {
  const g = (grade || "F").toUpperCase()[0];
  if (g === "A" || g === "B") return BRAND;
  if (g === "C") return "#FBBF24";
  return "#F87171";
}

function ScoreRing({ score, grade }: { score: number; grade: string }) {
  const r = 46;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const offset = c * (1 - pct);
  const stroke = gradeStroke(grade);
  return (
    <div className="relative mx-auto h-[140px] w-[140px] shrink-0">
      <svg width="140" height="140" viewBox="0 0 120 120" className="block" aria-hidden>
        <circle cx="60" cy="60" r={r} fill="none" stroke="#1A1727" strokeWidth="10" />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke={stroke}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform="rotate(-90 60 60)"
          className="transition-[stroke-dashoffset] duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-3xl font-extrabold tracking-tight text-text-primary">{score}</span>
        <span className="text-xs text-text-secondary">/ 100</span>
      </div>
    </div>
  );
}

const PROGRESS_LINES = [
  "Checking email security (DMARC/SPF/DKIM)...",
  "Checking SSL certificate...",
  "Checking for data breaches...",
  "Running vulnerability analysis...",
];

export function HomeScanner() {
  const [domain, setDomain] = useState("");
  const [phase, setPhase] = useState<"idle" | "scanning" | "done">("idle");
  const [tickSlot, setTickSlot] = useState(0);
  const [result, setResult] = useState<PublicScanResult | null>(null);
  const [scanFailed, setScanFailed] = useState(false); // API error — still offer email capture only
  const [showSlowLead, setShowSlowLead] = useState(false);
  const [email, setEmail] = useState("");
  const [emailSlow, setEmailSlow] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [emailSentSlow, setEmailSentSlow] = useState(false);
  const resultRef = useRef<PublicScanResult | null>(null);
  const slowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearSlowTimer = () => {
    if (slowTimerRef.current) {
      clearTimeout(slowTimerRef.current);
      slowTimerRef.current = null;
    }
  };

  const submitLead = useCallback(
    async (addr: string, plain: string[], res: PublicScanResult | null) => {
      const d = normalizeDomain(domain);
      const top = plain[0] || res?.findings_plain?.[0] || null;
      await marketingApi.homepageLead({
        email: addr.trim(),
        domain: d,
        hawk_score: res?.score ?? null,
        grade: res?.grade ?? null,
        top_finding: top,
        findings_plain: plain.length ? plain : res?.findings_plain || [],
      });
    },
    [domain],
  );

  const onScan = async () => {
    const d = normalizeDomain(domain);
    if (!d || !d.includes(".")) return;
    setPhase("scanning");
    setResult(null);
    setScanFailed(false);
    setShowSlowLead(false);
    setEmailSent(false);
    setEmailSentSlow(false);
    resultRef.current = null;
    setTickSlot(0);
    clearSlowTimer();

    slowTimerRef.current = setTimeout(() => {
      if (!resultRef.current) setShowSlowLead(true);
    }, 15000);

    const tick = setInterval(() => {
      setTickSlot((s) => Math.min(s + 1, 3));
    }, 2600);

    try {
      const res = await scansApi.startPublic({ domain: d, scan_depth: "fast" });
      resultRef.current = res;
      setResult(res);
      setShowSlowLead(false);
      setPhase("done");
    } catch (e) {
      console.error(e);
      setScanFailed(true);
      setShowSlowLead(true);
      setPhase("done");
      clearSlowTimer();
    } finally {
      clearInterval(tick);
      clearSlowTimer();
    }
  };

  useEffect(() => {
    return () => clearSlowTimer();
  }, []);

  const plain = result?.findings_plain || [];
  const issues = result?.issues_count ?? result?.findings_count ?? 0;
  const dnorm = normalizeDomain(domain);

  const onSubmitMainEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    await submitLead(email, plain, result);
    setEmailSent(true);
  };

  const onSubmitSlowEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailSlow.trim()) return;
    await submitLead(emailSlow, [], result);
    setEmailSentSlow(true);
  };

  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
        <Input
          placeholder="yourbusiness.com"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && phase === "idle" && onScan()}
          disabled={phase === "scanning"}
          className="h-12 border-surface-3 bg-surface-1 text-base"
        />
        <Button
          type="button"
          onClick={onScan}
          disabled={phase === "scanning" || !normalizeDomain(domain).includes(".")}
          className="h-12 shrink-0 px-6 font-semibold text-white bg-accent hover:bg-accent/90 sm:min-w-[200px]"
        >
          {phase === "scanning" ? "Scanning…" : "Scan My Domain Free"}
        </Button>
      </div>

      {phase === "scanning" && (
        <div
          className="mt-8 rounded-xl border border-surface-3 bg-surface-1 px-4 py-5 text-left text-sm"
          role="status"
          aria-live="polite"
        >
          {PROGRESS_LINES.map((line, i) => {
            const done = i < 3 && tickSlot > i;
            const spinning = i === 3 && tickSlot >= 3;
            return (
              <div
                key={line}
                className={cn("flex gap-2 py-1.5 text-text-secondary", (done || spinning) && "text-accent")}
              >
                <span className="w-5 shrink-0 font-mono text-xs" aria-hidden>
                  {done ? "✓" : spinning ? "⟳" : "·"}
                </span>
                <span>{line}</span>
              </div>
            );
          })}
        </div>
      )}

      {phase === "done" && !result && (showSlowLead || scanFailed) && (
        <div className="mt-10 space-y-4 rounded-xl border border-surface-3 bg-surface-1 p-6">
          {scanFailed ? (
            <p className="text-text-secondary leading-relaxed">
              We could not finish the instant preview. Enter your email and we will run your scan and send the full report shortly.
            </p>
          ) : (
            <p className="text-text-primary leading-relaxed">
              Our scanner is running your full analysis.
              <br />
              <br />
              This takes a few minutes for a thorough check.
              <br />
              <br />
              Enter your email and we will send you the complete report the moment it is ready.
            </p>
          )}
          {emailSentSlow ? (
            <p className="text-sm text-accent font-medium">
              Check your inbox in 5 minutes. We are running your full security analysis now.
            </p>
          ) : (
            <form onSubmit={onSubmitSlowEmail} className="flex flex-col gap-3 sm:flex-row">
              <Input
                type="email"
                required
                placeholder="you@company.com"
                value={emailSlow}
                onChange={(e) => setEmailSlow(e.target.value)}
                className="h-12 border-surface-3 bg-background"
              />
              <Button type="submit" className="h-12 font-semibold text-white bg-accent hover:bg-accent/90 sm:shrink-0">
                Send Me The Results
              </Button>
            </form>
          )}
        </div>
      )}

      {phase === "done" && result && !scanFailed && (
        <div className="mt-10 space-y-8">
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start sm:justify-center sm:gap-10">
            <ScoreRing score={result.score ?? 0} grade={result.grade || "F"} />
            <div className="text-center sm:text-left">
              <p className="text-sm uppercase tracking-wider text-text-dim">Grade</p>
              <p className="text-5xl font-extrabold tabular-nums" style={{ color: gradeStroke(result.grade) }}>
                {result.grade || "—"}
              </p>
              <p className="mt-2 text-sm text-text-secondary">Fast scan — full report in your inbox</p>
            </div>
          </div>

          <div>
            <h3 className="mb-4 text-lg font-semibold text-text-primary">
              Top findings found on {result.domain || dnorm}:
            </h3>
            <ul className="space-y-3 text-text-secondary">
              {plain.slice(0, 3).map((line, i) => (
                <li key={i} className="flex gap-2 border-l-2 border-accent/40 pl-4 leading-relaxed">
                  <span className="text-accent" aria-hidden>
                    •
                  </span>
                  <span>{line}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-surface-3 bg-surface-1 p-6">
            <p className="text-text-primary leading-relaxed">
              We found {issues} security {issues === 1 ? "issue" : "issues"} on {result.domain || dnorm}.
              <br />
              <br />
              We are running a deeper 60-point analysis right now.
              <br />
              <br />
              Enter your email and we will send you the full report within 5 minutes — free.
            </p>
            {emailSent ? (
              <p className="mt-4 text-sm text-accent font-medium">
                Check your inbox in 5 minutes. We are running your full security analysis now.
              </p>
            ) : (
              <form onSubmit={onSubmitMainEmail} className="mt-6 flex flex-col gap-3 sm:flex-row">
                <Input
                  type="email"
                  required
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-12 border-surface-3 bg-background"
                />
                <Button type="submit" className="h-12 font-semibold text-white bg-accent hover:bg-accent/90 sm:shrink-0">
                  Send Me The Full Report
                </Button>
              </form>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
