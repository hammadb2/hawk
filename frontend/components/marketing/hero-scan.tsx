"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  HttpError,
  marketingApi,
  scansApi,
  type PublicScanFindingPreview,
  type PublicScanResult,
} from "@/lib/api";

type Phase = "idle" | "scanning" | "revealed" | "failed";

const DOMAIN_RE = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/i;

function normalizeDomain(raw: string): string {
  let d = raw.trim().toLowerCase();
  if (!d) return "";
  if (d.startsWith("http://") || d.startsWith("https://")) {
    try {
      d = new URL(d).hostname;
    } catch {
      /* keep raw */
    }
  }
  if (d.startsWith("www.")) d = d.slice(4);
  return d.split("/")[0];
}

function severityLabel(s: string | undefined): { label: string; tone: "hot" | "warm" | "cool" } {
  const v = (s || "medium").toLowerCase();
  if (v === "critical" || v === "high") return { label: v === "critical" ? "Critical" : "High", tone: "hot" };
  if (v === "medium" || v === "warning") return { label: "Medium", tone: "warm" };
  if (v === "low") return { label: "Low", tone: "warm" };
  return { label: "Info", tone: "cool" };
}

const SCAN_PROGRESS_LINES = [
  "Mapping exposed hostnames and listening ports.",
  "Inspecting TLS chains, ciphers, and certificate posture.",
  "Verifying SPF, DKIM, and DMARC against spoofing playbooks.",
  "Cross referencing leaked credentials and stealer logs.",
  "Probing known exploit classes for your stack.",
  "Ranking findings by blast radius and remediation cost.",
];

export function HeroScan() {
  const [domain, setDomain] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<PublicScanResult | null>(null);
  const [progressIdx, setProgressIdx] = useState(0);
  const [email, setEmail] = useState("");
  const [reportStatus, setReportStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [reportError, setReportError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const nd = normalizeDomain(domain);
  const canScan = DOMAIN_RE.test(nd) && phase !== "scanning";

  useEffect(() => {
    if (phase !== "scanning") return;
    intervalRef.current = setInterval(() => {
      setProgressIdx((i) => (i + 1) % SCAN_PROGRESS_LINES.length);
    }, 1600);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [phase]);

  const reset = useCallback(() => {
    setPhase("idle");
    setResult(null);
    setProgressIdx(0);
    setReportStatus("idle");
    setReportError(null);
  }, []);

  const runScan = useCallback(async () => {
    if (!canScan) return;
    setPhase("scanning");
    setResult(null);
    setProgressIdx(0);
    setReportStatus("idle");
    setReportError(null);
    try {
      const res = await scansApi.startPublic({ domain: nd, scan_depth: "fast" });
      setResult(res);
      setPhase("revealed");
    } catch {
      setPhase("failed");
    }
  }, [canScan, nd]);

  const sendReport = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!email.trim() || !nd || reportStatus === "sending") return;
      setReportStatus("sending");
      setReportError(null);
      try {
        await marketingApi.freeScan({
          email: email.trim(),
          domain: nd,
          company_name: undefined,
          name: undefined,
          vertical: undefined,
        });
        setReportStatus("sent");
      } catch (err) {
        let msg = "We could not queue the report. Try again in a minute.";
        if (err instanceof HttpError) {
          if (err.status === 429) msg = "Too many requests. Try again in a minute.";
          else if (err.status === 400 || err.status === 422) msg = "Double check the email and domain.";
        }
        setReportError(msg);
        setReportStatus("error");
      }
    },
    [email, nd, reportStatus],
  );

  const previewRows: PublicScanFindingPreview[] =
    result?.findings_preview?.length && result.findings_preview.length > 0
      ? result.findings_preview.slice(0, 3)
      : (result?.findings_plain || [])
          .slice(0, 3)
          .map((text) => ({ text, severity: "medium" } as PublicScanFindingPreview));

  const insuranceReadiness =
    typeof result?.insurance_readiness === "number"
      ? result.insurance_readiness
      : typeof result?.score === "number"
      ? result.score
      : null;

  return (
    <div className="relative w-full max-w-xl">
      {/* Amber glow ring behind the widget */}
      <div aria-hidden className="absolute inset-[-28px] rounded-[28px] bg-signal/10 blur-3xl opacity-70" />

      <div className="relative rounded-2xl border border-white/10 bg-ink-800/70 p-2 shadow-ink backdrop-blur-xl">
        {/* Domain input row */}
        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-stretch"
          onSubmit={(e) => {
            e.preventDefault();
            runScan();
          }}
        >
          <label htmlFor="hero-domain" className="sr-only">
            Enter your business domain
          </label>
          <div className="flex min-w-0 flex-1 items-center gap-3 rounded-xl bg-ink-900/80 px-4 py-3.5 ring-1 ring-inset ring-white/5 focus-within:ring-signal/60 transition-all">
            <DomainGlyph />
            <input
              id="hero-domain"
              name="domain"
              type="text"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              disabled={phase === "scanning"}
              placeholder="yourpractice.com"
              value={domain}
              onChange={(e) => {
                setDomain(e.target.value);
                if (phase === "revealed" || phase === "failed") reset();
              }}
              className="w-full bg-transparent text-base font-medium text-ink-0 placeholder:text-ink-300 focus:outline-none disabled:opacity-60"
            />
          </div>
          <button
            type="submit"
            disabled={!canScan}
            className="group inline-flex items-center justify-center gap-2 rounded-xl bg-signal px-6 py-3.5 text-sm font-semibold tracking-wide text-ink-950 shadow-signal-sm transition-all hover:bg-signal-400 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {phase === "scanning" ? (
              <>
                <Spinner />
                Scanning
              </>
            ) : (
              <>
                Run free scan
                <ArrowRightGlyph />
              </>
            )}
          </button>
        </form>

        <p className="mt-3 px-2 pb-1 text-xs text-ink-200">
          In 2025, OCR issued over $6.6M in HIPAA fines — mostly for failures a scan would have caught.
        </p>
      </div>

      {/* Reveal panel */}
      <AnimatePresence mode="wait">
        {phase === "scanning" && (
          <motion.div
            key="scanning"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="mt-5 overflow-hidden rounded-2xl border border-white/5 bg-ink-800/50 p-5 backdrop-blur"
          >
            <div className="flex items-center gap-3">
              <PulseDot />
              <span className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">
                Live scan in progress
              </span>
            </div>
            <AnimatePresence mode="wait">
              <motion.p
                key={progressIdx}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.35 }}
                className="mt-4 text-sm text-ink-100"
              >
                {SCAN_PROGRESS_LINES[progressIdx]}
              </motion.p>
            </AnimatePresence>
            <ScanProgressBar />
          </motion.div>
        )}

        {phase === "revealed" && result && (
          <motion.div
            key="revealed"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            className="mt-5 overflow-hidden rounded-2xl border border-white/5 bg-ink-800/55 backdrop-blur-xl"
          >
            <div className="border-b border-white/5 px-5 py-4">
              <div className="flex items-center gap-3">
                <GradeChip grade={result.grade || "C"} />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink-0">{nd}</p>
                  <p className="text-xs text-ink-200">
                    HAWK score {result.score ?? "n/a"}. {result.issues_count ?? result.findings_count ?? previewRows.length} findings surfaced.
                  </p>
                </div>
              </div>
              {(result.score ?? 100) < 80 && (
                <p className="mt-3 text-xs leading-relaxed text-red">
                  A score below 80 puts your practice at elevated risk of HIPAA enforcement action.
                </p>
              )}
              <InsuranceReadiness value={insuranceReadiness} />
              {result.ransomware_intel && (
                <div className="mt-4 rounded-lg border border-red/20 bg-red/5 px-3 py-2.5">
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-red">
                    Ransomware intel
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-ink-100">
                    {result.ransomware_intel}
                  </p>
                </div>
              )}
            </div>

            <ul className="divide-y divide-white/5">
              {previewRows.map((row, i) => {
                const { label, tone } = severityLabel(row.severity);
                const controls = hipaaControlsFor(row);
                return (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.12 * i, ease: [0.22, 1, 0.36, 1] }}
                    className="flex items-start gap-3 px-5 py-4"
                  >
                    <SeverityChip tone={tone} label={label} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm leading-relaxed text-ink-0">{row.text}</p>
                      {controls.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {controls.map((c) => (
                            <span
                              key={c}
                              className="inline-flex items-center rounded-md border border-signal/30 bg-signal/10 px-2 py-0.5 text-[10px] font-medium text-signal"
                            >
                              Violates {c}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </motion.li>
                );
              })}
            </ul>

            <div className="border-t border-white/5 bg-ink-900/60 px-5 py-5">
              {reportStatus === "sent" ? (
                <div className="flex items-start gap-3">
                  <CheckDot />
                  <p className="text-sm text-ink-0">
                    Queued. A plain English report with the three highest priority findings lands in
                    your inbox within 24 hours.
                  </p>
                </div>
              ) : (
                <>
                  <p className="mb-3 text-xs text-ink-200">
                    No credit card. No sales call. Report in your inbox within 24 hours.
                  </p>
                  <form className="flex flex-col gap-2 sm:flex-row" onSubmit={sendReport}>
                    <label htmlFor="hero-report-email" className="sr-only">
                      Email address
                    </label>
                    <input
                      id="hero-report-email"
                      type="email"
                      required
                      autoComplete="email"
                      disabled={reportStatus === "sending"}
                      placeholder="you@yourpractice.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="flex-1 rounded-xl bg-ink-700/80 px-4 py-3 text-sm font-medium text-ink-0 ring-1 ring-inset ring-white/5 placeholder:text-ink-300 focus:outline-none focus:ring-signal/60 disabled:opacity-60"
                    />
                    <button
                      type="submit"
                      disabled={!email.trim() || reportStatus === "sending"}
                      className="inline-flex items-center justify-center rounded-xl bg-signal px-5 py-3 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400 disabled:opacity-40"
                    >
                      {reportStatus === "sending" ? "Queuing" : "Get my full report \u2014 free"}
                    </button>
                  </form>
                </>
              )}
              {reportStatus === "error" && reportError && (
                <p className="mt-2 text-xs text-red">{reportError}</p>
              )}
            </div>
          </motion.div>
        )}

        {phase === "failed" && (
          <motion.div
            key="failed"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
            className="mt-5 rounded-2xl border border-red/20 bg-red/5 p-5 text-sm text-ink-100"
          >
            {reportStatus === "sent" ? (
              <div className="flex items-start gap-3">
                <CheckDot />
                <p className="text-sm text-ink-0">
                  Queued. A plain English report with the three highest priority findings lands in
                  your inbox within 24 hours.
                </p>
              </div>
            ) : (
              <>
                The live scan timed out for this domain. Enter your email and we will run the full
                24 hour report in the background.
                <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={sendReport}>
                  <label htmlFor="hero-report-email-failed" className="sr-only">
                    Email address
                  </label>
                  <input
                    id="hero-report-email-failed"
                    type="email"
                    required
                    autoComplete="email"
                    disabled={reportStatus === "sending"}
                    placeholder="you@yourpractice.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="flex-1 rounded-xl bg-ink-700/80 px-4 py-3 text-sm font-medium text-ink-0 ring-1 ring-inset ring-white/5 placeholder:text-ink-300 focus:outline-none focus:ring-signal/60 disabled:opacity-60"
                  />
                  <button
                    type="submit"
                    disabled={!email.trim() || reportStatus === "sending"}
                    className="inline-flex items-center justify-center rounded-xl bg-signal px-5 py-3 text-sm font-semibold text-ink-950 transition-colors hover:bg-signal-400 disabled:opacity-40"
                  >
                    {reportStatus === "sending" ? "Queuing" : "Queue the report"}
                  </button>
                </form>
                {reportStatus === "error" && reportError && (
                  <p className="mt-2 text-xs text-red">{reportError}</p>
                )}
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DomainGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="shrink-0 text-signal" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M3 12h18M12 3a15 15 0 0 1 4 9 15 15 0 0 1-4 9 15 15 0 0 1-4-9 15 15 0 0 1 4-9Z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function ArrowRightGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M5 12h14m0 0l-6-6m6 6l-6 6" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
        <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.85s" repeatCount="indefinite" />
      </path>
    </svg>
  );
}

function PulseDot() {
  return <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-signal shadow-[0_0_12px_rgba(255,184,0,0.7)] animate-signal-pulse" />;
}

function CheckDot() {
  return (
    <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-signal/20 text-signal">
      <svg width="12" height="12" viewBox="0 0 20 20" fill="none" aria-hidden>
        <path d="M4 10.5l4 4 8-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function GradeChip({ grade }: { grade: string }) {
  const g = (grade || "C").toUpperCase()[0];
  const color = g === "A" || g === "B" ? "text-signal" : g === "C" ? "text-orange" : "text-red";
  return (
    <span
      className={`inline-flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-ink-900 font-display text-2xl font-bold ${color}`}
      aria-label={`Score grade ${g}`}
    >
      {g}
    </span>
  );
}

function SeverityChip({ tone, label }: { tone: "hot" | "warm" | "cool"; label: string }) {
  const cls =
    tone === "hot"
      ? "bg-red/15 text-red ring-red/30"
      : tone === "warm"
      ? "bg-signal/15 text-signal ring-signal/30"
      : "bg-ink-700 text-ink-100 ring-white/10";
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest ring-1 ring-inset ${cls}`}
    >
      {label}
    </span>
  );
}

function InsuranceReadiness({ value }: { value: number | null }) {
  if (value == null) return null;
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-ink-200">
          Insurance Readiness Score
        </p>
        <span className="font-display text-sm font-semibold text-ink-0">{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Insurance readiness score"
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-700"
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-signal-600 via-signal to-signal-200 transition-[width] duration-700"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-ink-100">
        {pct >= 80
          ? "Your posture is strong \u2014 maintain it to keep cyber insurance premiums in check."
          : "Your current posture will likely increase your cyber insurance premium."}
      </p>
    </div>
  );
}

/**
 * HIPAA 2026 Security Rule citation mapping.
 *
 * Prefers the backend's `hipaa_controls` array when present. When absent, we
 * derive a citation from the finding text so the "Violates HIPAA §… — 2026
 * Security Rule" tag always matches what the finding actually describes
 * (rather than slapping the same citation on every first finding).
 *
 * Returns [] when no mapping is confident, so the widget silently omits the
 * tag instead of making a false compliance claim.
 */
const HIPAA_2026_MAP: Array<{ match: RegExp; citation: string }> = [
  {
    match: /\b(tls|ssl|cipher|https|cert(?:ificate)?|hsts)/i,
    citation: "HIPAA §164.312(e)(1) — 2026 Security Rule",
  },
  {
    match: /\b(spf|dkim|dmarc|email spoof|mail server)/i,
    citation: "HIPAA §164.312(e)(2)(ii) — 2026 Security Rule",
  },
  {
    match: /\b(credential|password|leaked|stealer|breach|mfa|multi[- ]?factor|authentication|auth\b)/i,
    citation: "HIPAA §164.312(d) — 2026 Security Rule",
  },
  {
    match: /\b(open port|listening|exposed (?:service|admin|rdp|ssh)|unauthoriz(?:ed|ed access))/i,
    citation: "HIPAA §164.312(a)(1) — 2026 Security Rule",
  },
  {
    match: /\b(log(?:s|ged|ging)?|audit(?:s|ed|ing)?|monitoring)\b/i,
    citation: "HIPAA §164.312(b) — 2026 Security Rule",
  },
];

function hipaaControlsFor(row: PublicScanFindingPreview): string[] {
  if (row.hipaa_controls && row.hipaa_controls.length > 0) return row.hipaa_controls;
  const hit = HIPAA_2026_MAP.find((m) => m.match.test(row.text));
  return hit ? [hit.citation] : [];
}

function ScanProgressBar() {
  return (
    <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-ink-700">
      <motion.div
        initial={{ width: "8%" }}
        animate={{ width: ["8%", "55%", "72%", "88%", "94%"] }}
        transition={{ duration: 14, ease: "easeInOut" }}
        className="h-full rounded-full bg-gradient-to-r from-signal-600 via-signal to-signal-200"
      />
    </div>
  );
}
