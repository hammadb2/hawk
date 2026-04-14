"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
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
        <circle cx="60" cy="60" r={r} fill="none" stroke="#e2e8f0" strokeWidth="10" />
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
        <span className="text-3xl font-extrabold tracking-tight text-slate-900">{score}</span>
        <span className="text-xs text-slate-600">/ 100</span>
      </div>
    </div>
  );
}

const PROGRESS_LINES = [
  { text: "Checking email security (DMARC / SPF / DKIM)…", emoji: "✉️" },
  { text: "Checking TLS & certificate on your edge…", emoji: "🔐" },
  { text: "Mapping subdomains, ports & web exposure…", emoji: "🌐" },
  { text: "Checking breach intel & correlating your score…", emoji: "⚡" },
];

const WAITING_TIPS = [
  "We never store your password — this is an external, read-only snapshot.",
  "Attackers use the same public data we are looking at right now.",
  "Canadian privacy laws care about email spoofing — we check that first.",
  "A slow response usually means we are going deeper, not skipping checks.",
];

function GlobeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="12" cy="12" r="10" className="text-slate-500" />
      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" className="text-slate-500" />
    </svg>
  );
}

export function HomeScanner() {
  const [domain, setDomain] = useState("");
  const [phase, setPhase] = useState<"idle" | "scanning" | "done">("idle");
  const [tickSlot, setTickSlot] = useState(0);
  const [tipIndex, setTipIndex] = useState(0);
  const [result, setResult] = useState<PublicScanResult | null>(null);
  const [scanFailed, setScanFailed] = useState(false);
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

  const preview = normalizeDomain(domain);
  const canSubmit = preview.includes(".");

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

  useEffect(() => {
    if (phase !== "scanning") return;
    const id = setInterval(() => {
      setTipIndex((i) => (i + 1) % WAITING_TIPS.length);
    }, 3800);
    return () => clearInterval(id);
  }, [phase]);

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
    setTipIndex(0);
    clearSlowTimer();

    slowTimerRef.current = setTimeout(() => {
      if (!resultRef.current) setShowSlowLead(true);
    }, 15000);

    const tick = setInterval(() => {
      setTickSlot((s) => Math.min(s + 1, 3));
    }, 2200);

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

  const onDomainChange = (v: string) => {
    setDomain(v);
    if (phase === "done") {
      setPhase("idle");
      setResult(null);
      setScanFailed(false);
      setShowSlowLead(false);
      setEmailSent(false);
      setEmailSentSlow(false);
    }
  };

  const progressPct = Math.min(100, 8 + tickSlot * 24 + (phase === "scanning" ? 8 : 0));

  return (
    <div className="w-full max-w-xl mx-auto px-1 sm:px-0">
      {/* Domain input — elevated card, icon, helper */}
      <div
        className={cn(
          "rounded-2xl border bg-white/95 p-3 sm:p-4 shadow-lg transition-all duration-300",
          phase === "scanning"
            ? "border-accent/40 shadow-accent/5"
            : "border-slate-200 focus-within:border-accent/50 focus-within:shadow-[0_0_0_3px_rgba(34,197,94,0.12)]",
        )}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch sm:gap-3">
          <div className="relative min-w-0 flex-1">
            <label htmlFor="hawk-domain-scan" className="sr-only">
              Domain to scan
            </label>
            <div
              className={cn(
                "flex h-14 items-center gap-3 rounded-xl border px-3 transition-colors sm:h-[3.25rem]",
                "border-slate-200 bg-slate-100/80",
                "focus-within:border-accent/55 focus-within:bg-slate-100",
              )}
            >
              <GlobeIcon className="h-5 w-5 shrink-0 text-accent/90" />
              <Input
                id="hawk-domain-scan"
                placeholder="yourbusiness.com"
                value={domain}
                onChange={(e) => onDomainChange(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && phase === "idle" && canSubmit && onScan()}
                disabled={phase === "scanning"}
                className="h-full min-w-0 flex-1 border-0 bg-transparent px-0 text-base text-slate-900 shadow-none placeholder:text-slate-500 focus-visible:ring-0 focus-visible:ring-offset-0 sm:text-lg"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
              />
            </div>
            <p className="mt-2 text-left text-xs leading-snug text-slate-500 sm:text-[13px]">
              Paste a URL or domain — we strip <span className="text-slate-600">https://</span> and{" "}
              <span className="text-slate-600">www.</span> automatically.
              {preview.length > 2 && canSubmit && (
                <span className="mt-1 block font-mono text-[11px] text-accent/90">→ scans as {preview}</span>
              )}
            </p>
          </div>
          <Button
            type="button"
            onClick={onScan}
            disabled={phase === "scanning" || !canSubmit}
            className="h-14 shrink-0 rounded-xl px-6 font-semibold text-white shadow-md transition-transform active:scale-[0.98] sm:h-[3.25rem] sm:min-w-[200px] sm:self-end"
          >
            {phase === "scanning" ? "Scanning…" : "Scan free"}
          </Button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {phase === "scanning" && (
          <motion.div
            key="scanning"
            role="status"
            aria-live="polite"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 380, damping: 28 }}
            className="relative mt-8 overflow-hidden rounded-2xl border border-accent/25 bg-gradient-to-b from-white via-slate-50 to-slate-100/95 px-4 py-6 shadow-xl sm:px-6"
          >
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_30%_0%,rgba(34,197,94,0.12),transparent_55%)]" />
            <div className="absolute inset-x-0 top-0 h-1 bg-slate-200">
              <motion.div
                className="h-full bg-gradient-to-r from-accent via-emerald-300 to-accent"
                initial={{ width: "0%" }}
                animate={{ width: `${progressPct}%` }}
                transition={{ type: "spring", stiffness: 120, damping: 18 }}
              />
            </div>

            <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:gap-6">
              <div className="flex shrink-0 justify-center sm:justify-start">
                <div className="relative h-[4.5rem] w-[4.5rem]">
                  <motion.div
                    className="absolute inset-0 rounded-full border-2 border-accent/25"
                    animate={{ scale: [1, 1.08, 1], opacity: [0.5, 0.85, 0.5] }}
                    transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
                  />
                  <motion.div
                    className="absolute inset-1 rounded-full border border-accent/40"
                    style={{ borderTopColor: BRAND, borderRightColor: "transparent" }}
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
                  />
                  <motion.div
                    className="absolute inset-0 flex items-center justify-center text-2xl"
                    animate={{ scale: [1, 1.12, 1] }}
                    transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                  >
                    🦅
                  </motion.div>
                </div>
              </div>
              <div className="min-w-0 flex-1 text-center sm:text-left">
                <p className="text-base font-semibold tracking-tight text-slate-900 sm:text-lg">
                  Scanning <span className="text-accent">{preview || "your domain"}</span>
                </p>
                <p className="mt-1 text-sm text-slate-600">Mapping what the internet already knows about you.</p>
                <AnimatePresence mode="wait">
                  <motion.p
                    key={tipIndex}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.35 }}
                    className="mt-3 text-xs italic leading-relaxed text-slate-500 sm:text-sm"
                  >
                    {WAITING_TIPS[tipIndex]}
                  </motion.p>
                </AnimatePresence>
              </div>
            </div>

            <ul className="relative mt-6 space-y-2 border-t border-slate-200/80 pt-5">
              {PROGRESS_LINES.map((row, i) => {
                const done = i < 3 && tickSlot > i;
                const active = (i === 3 && tickSlot >= 3) || (i < 3 && tickSlot === i);
                const pending = !done && !active;
                return (
                  <motion.li
                    key={row.text}
                    initial={false}
                    animate={{
                      opacity: done ? 1 : active ? 1 : 0.45,
                      x: done ? 0 : active ? 2 : 0,
                    }}
                    className={cn(
                      "flex items-start gap-3 rounded-lg py-2 pl-1 text-sm sm:text-[15px]",
                      done && "text-accent",
                      active && "bg-accent/5 text-slate-900",
                      pending && "text-slate-500",
                    )}
                  >
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-base" aria-hidden>
                      {done ? "✓" : active ? "✨" : "○"}
                    </span>
                    <span>
                      <span className="mr-2 select-none" aria-hidden>
                        {row.emoji}
                      </span>
                      {row.text}
                    </span>
                    {active && (
                      <motion.span
                        className="ml-auto hidden h-2 w-12 overflow-hidden rounded-full bg-slate-200 sm:block"
                        aria-hidden
                      >
                        <motion.span
                          className="block h-full w-1/2 rounded-full bg-accent"
                          animate={{ x: ["-100%", "200%"] }}
                          transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
                        />
                      </motion.span>
                    )}
                  </motion.li>
                );
              })}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>

      {phase === "done" && !result && (showSlowLead || scanFailed) && (
        <div className="mt-10 space-y-4 rounded-xl border border-slate-200 bg-white p-6">
          {scanFailed ? (
            <p className="text-slate-600 leading-relaxed">
              We could not finish the instant preview. Enter your email and we will run your scan and send the full report shortly.
            </p>
          ) : (
            <p className="text-slate-900 leading-relaxed">
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
                className="h-12 border-slate-200 bg-white text-slate-900 placeholder:text-slate-400"
              />
              <Button type="submit" className="h-12 font-semibold text-white bg-accent hover:bg-accent/90 sm:shrink-0">
                Send Me The Results
              </Button>
            </form>
          )}
        </div>
      )}

      {phase === "done" && result && !scanFailed && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="mt-10 space-y-8"
        >
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start sm:justify-center sm:gap-10">
            <ScoreRing score={result.score ?? 0} grade={result.grade || "F"} />
            <div className="text-center sm:text-left">
              <p className="text-sm uppercase tracking-wider text-slate-500">Grade</p>
              <p className="text-5xl font-extrabold tabular-nums" style={{ color: gradeStroke(result.grade) }}>
                {result.grade || "—"}
              </p>
              <p className="mt-2 text-sm text-slate-600">
                Free instant scan — HAWK Engine{" "}
                {result.scan_version === "2.1-fast" ? "2.1 snapshot" : result.scan_version ?? "2.1"}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-accent/20 bg-gradient-to-br from-white to-slate-100/90 p-5 shadow-lg sm:p-6">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-accent">Go deeper — paid HAWK Shield</p>
                <h3 className="mt-1 text-lg font-bold text-slate-900 sm:text-xl">Turn this snapshot into continuous protection</h3>
                <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-600">
                  Your free scan already runs email, TLS, breach intelligence, subdomain discovery, targeted ports, HTTP probes,
                  and Internet-wide exposure hints. Shield adds{" "}
                  <strong className="text-slate-900">Nuclei template coverage</strong>,{" "}
                  <strong className="text-slate-900">lookalike domain monitoring</strong>, scheduled re-scans, and the
                  breach-response guarantee on this page — the bundle SMBs buy when insurers and clients ask hard questions.
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Free instant scan</p>
                <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
                  <li>✓ Email auth & TLS deep check</li>
                  <li>✓ Multi-source breach / stealer signals</li>
                  <li>✓ Subdomains + ports + HTTP surface</li>
                  <li>✓ InternetDB exposure hints</li>
                </ul>
              </div>
              <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-accent">HAWK Shield (paid)</p>
                <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
                  <li>✓ Full Nuclei vulnerability templates</li>
                  <li>✓ dnstwist lookalike monitoring</li>
                  <li>✓ Scheduled scans & history</li>
                  <li>✓ Breach response guarantee — in writing</li>
                </ul>
              </div>
            </div>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row">
              <Button
                asChild
                className="h-12 flex-1 rounded-xl font-semibold text-white shadow-md bg-accent hover:bg-accent/90"
              >
                <Link href="/portal/login?next=%2Fportal%2Fbilling%3Fplan%3Dshield">Start Shield — most popular</Link>
              </Button>
              <Button asChild variant="outline" className="h-12 flex-1 rounded-xl border-slate-200 bg-white font-semibold text-slate-900 hover:bg-slate-50">
                <Link href="#pricing">Compare all plans</Link>
              </Button>
            </div>
          </div>

          <div>
            <h3 className="mb-4 text-lg font-semibold text-slate-900">
              Top findings found on {result.domain || dnorm}:
            </h3>
            <ul className="space-y-3 text-slate-600">
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

          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <p className="text-slate-900 leading-relaxed">
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
                  className="h-12 border-slate-200 bg-white text-slate-900 placeholder:text-slate-400"
                />
                <Button type="submit" className="h-12 font-semibold text-white bg-accent hover:bg-accent/90 sm:shrink-0">
                  Send Me The Full Report
                </Button>
              </form>
            )}
          </div>
        </motion.div>
      )}
    </div>
  );
}
