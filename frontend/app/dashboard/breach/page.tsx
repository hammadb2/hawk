"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/providers/auth-provider";
import { breachApi, type BreachCheckResponse, type EmailBreachResult } from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_EMAILS = 50;
const SECONDS_PER_EMAIL = 1.65; // HIBP rate limit

function parseEmails(raw: string): string[] {
  return raw
    .split(/[\n,;]+/)
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

// ── Summary stat card ──────────────────────────────────────────────────────
function StatCard({ label, value, sub, variant = "neutral" }: {
  label: string;
  value: number | string;
  sub?: string;
  variant?: "neutral" | "danger" | "safe";
}) {
  return (
    <div className={cn(
      "rounded-xl border p-5 text-center",
      variant === "danger" ? "border-red/40 bg-red/10" :
      variant === "safe"   ? "border-green/30 bg-green/10" :
                             "border-surface-3 bg-surface-2"
    )}>
      <p className={cn(
        "text-4xl font-extrabold",
        variant === "danger" ? "text-red" :
        variant === "safe"   ? "text-green" :
                               "text-text-primary"
      )}>{value}</p>
      <p className="mt-1 text-sm font-medium text-text-secondary">{label}</p>
      {sub && <p className="mt-0.5 text-xs text-text-dim">{sub}</p>}
    </div>
  );
}

// ── Progress bar ───────────────────────────────────────────────────────────
function ProgressBar({ emailCount, running }: { emailCount: number; running: boolean }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const total = Math.ceil(emailCount * SECONDS_PER_EMAIL);

  useEffect(() => {
    if (!running) {
      setElapsed(0);
      startRef.current = null;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    startRef.current = Date.now();
    const tick = () => {
      if (startRef.current) {
        setElapsed(Math.min((Date.now() - startRef.current) / 1000, total));
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [running, total]);

  const pct = total > 0 ? Math.min((elapsed / total) * 100, 97) : 0; // cap at 97% until done
  const remaining = Math.max(Math.ceil(total - elapsed), 0);

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs text-text-secondary">
        <span>Checking {emailCount} email{emailCount !== 1 ? "s" : ""} against HaveIBeenPwned…</span>
        <span>~{remaining}s remaining</span>
      </div>
      <div className="h-2 rounded-full bg-surface-3 overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-accent"
          initial={{ width: "0%" }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: "linear" }}
        />
      </div>
      <p className="text-xs text-text-dim text-center">
        Checking ~1 email/sec to respect API rate limits. Do not close this tab.
      </p>
    </div>
  );
}

// ── Per-email expandable row ───────────────────────────────────────────────
function EmailRow({ result }: { result: EmailBreachResult }) {
  const [open, setOpen] = useState(false);

  const dotColor = result.error
    ? "bg-orange"
    : result.breached
    ? "bg-red"
    : "bg-green";

  return (
    <div className="rounded-lg border border-surface-3 bg-surface-2 overflow-hidden">
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-surface-3 transition-colors"
        aria-expanded={open}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={cn("inline-block w-2 h-2 rounded-full flex-shrink-0", dotColor)} />
          <span className="text-sm font-mono text-text-primary truncate">{result.email}</span>
          {result.error && <span className="text-xs text-orange">check failed</span>}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {result.breached && (
            <span className="text-xs font-semibold text-red bg-red/10 border border-red/30 rounded px-2 py-0.5">
              {result.breach_count} breach{result.breach_count !== 1 ? "es" : ""}
            </span>
          )}
          {!result.breached && !result.error && (
            <span className="text-xs font-semibold text-green bg-green/10 border border-green/30 rounded px-2 py-0.5">
              Clean
            </span>
          )}
          <span className="text-text-dim text-xs select-none">{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {open && result.breached && result.breaches.length > 0 && (
        <div className="border-t border-surface-3 px-4 py-3 space-y-3">
          {result.breaches.map((b) => (
            <div key={b.name} className="rounded border border-surface-3 bg-background p-3 text-sm space-y-1.5">
              <div className="flex items-start justify-between gap-2">
                <span className="font-semibold text-text-primary">{b.title || b.name}</span>
                <span className="text-xs text-text-dim whitespace-nowrap">{b.breach_date}</span>
              </div>
              {b.data_classes.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {b.data_classes.map((dc) => (
                    <span key={dc} className="text-xs bg-surface-3 text-text-secondary rounded px-1.5 py-0.5">
                      {dc}
                    </span>
                  ))}
                </div>
              )}
              <p className="text-xs text-text-dim">
                {b.pwn_count.toLocaleString()} accounts affected
                {!b.is_verified && " · unverified"}
              </p>
            </div>
          ))}
        </div>
      )}

      {open && result.error && (
        <div className="border-t border-surface-3 px-4 py-3 text-sm text-orange">
          Error: {result.error}
        </div>
      )}

      {open && !result.breached && !result.error && (
        <div className="border-t border-surface-3 px-4 py-3 text-sm text-green">
          No breach records found for this address.
        </div>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function BreachCheckPage() {
  const { token } = useAuth();
  const [domain, setDomain] = useState("");
  const [emailsRaw, setEmailsRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BreachCheckResponse | null>(null);

  const emails = parseEmails(emailsRaw);
  const tooMany = emails.length > MAX_EMAILS;
  const estimatedSecs = Math.ceil(emails.length * SECONDS_PER_EMAIL);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !domain.trim() || emails.length === 0 || tooMany) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await breachApi.check(
        { domain: domain.trim().toLowerCase(), emails },
        token,
      );
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Breach check failed");
    } finally {
      setLoading(false);
    }
  };

  const breachedResults = result?.results.filter((r) => r.breached) ?? [];
  const cleanResults   = result?.results.filter((r) => !r.breached && !r.error) ?? [];
  const errorResults   = result?.results.filter((r) => r.error) ?? [];

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Breach Check</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Find out how many staff email addresses from your domain appear in known data breaches — powered by{" "}
          <span className="text-text-primary font-medium">HaveIBeenPwned</span>.
        </p>
      </div>

      {/* Input form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Check Staff Emails</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Domain */}
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Company Domain
              </label>
              <input
                type="text"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="acme.com"
                disabled={loading}
                className="w-full rounded-lg border border-surface-3 bg-background px-3 py-2 text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50"
                required
              />
              <p className="mt-1 text-xs text-text-dim">
                All emails must belong to this domain.
              </p>
            </div>

            {/* Emails */}
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Staff Email Addresses{" "}
                <span className={cn("font-normal text-xs", tooMany ? "text-red" : "text-text-dim")}>
                  {emails.length > 0 ? `${emails.length} / ${MAX_EMAILS}` : `max ${MAX_EMAILS}`}
                </span>
              </label>
              <textarea
                value={emailsRaw}
                onChange={(e) => setEmailsRaw(e.target.value)}
                rows={6}
                disabled={loading}
                placeholder={"alice@acme.com\nbob@acme.com\ncarol@acme.com"}
                className="w-full rounded-lg border border-surface-3 bg-background px-3 py-2 text-sm font-mono text-text-primary placeholder:text-text-dim focus:outline-none focus:ring-2 focus:ring-accent resize-y disabled:opacity-50"
              />
              <p className="mt-1 text-xs text-text-dim">
                One per line, or comma/semicolon separated.
                {emails.length > 1 && !tooMany && (
                  <span className="ml-2 text-text-secondary">
                    Estimated check time: ~{estimatedSecs}s
                  </span>
                )}
              </p>
              {tooMany && (
                <p className="mt-1 text-xs text-red">
                  Too many emails — reduce to {MAX_EMAILS} or fewer.
                </p>
              )}
            </div>

            {error && (
              <div className="text-sm text-red rounded-lg border border-red/30 bg-red/10 px-3 py-2">
                {error}
              </div>
            )}

            {/* Progress bar shown while loading */}
            {loading && <ProgressBar emailCount={emails.length} running={loading} />}

            <Button
              type="submit"
              disabled={loading || !domain.trim() || emails.length === 0 || tooMany}
              className="w-full"
            >
              {loading ? "Checking breaches…" : "Run Breach Check"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      {result && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="space-y-5"
        >
          <h2 className="text-lg font-semibold text-text-primary">
            Results for{" "}
            <span className="font-mono text-accent">{result.domain}</span>
          </h2>

          {/* Summary stats */}
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Checked" value={result.total_checked} variant="neutral" />
            <StatCard
              label="Breached"
              value={result.breached_count}
              variant={result.breached_count > 0 ? "danger" : "neutral"}
            />
            <StatCard
              label="Clean"
              value={result.clean_count}
              variant={result.clean_count === result.total_checked ? "safe" : "neutral"}
            />
          </div>

          {/* Alert banner */}
          {result.breached_count > 0 && (
            <div className="rounded-lg border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">
              <strong>{result.breached_count} of {result.total_checked} staff email{result.total_checked !== 1 ? "s" : ""}</strong>
              {" "}appeared in known data breaches. Instruct affected staff to change passwords
              and enable MFA immediately.
            </div>
          )}

          {result.breached_count === 0 && errorResults.length === 0 && (
            <div className="rounded-lg border border-green/30 bg-green/10 px-4 py-3 text-sm text-green">
              All {result.total_checked} email{result.total_checked !== 1 ? "s" : ""} came back clean — no breach records found.
            </div>
          )}

          {/* Breached first, then clean */}
          {breachedResults.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-red">
                Breached ({breachedResults.length})
              </p>
              {breachedResults
                .slice()
                .sort((a, b) => b.breach_count - a.breach_count)
                .map((r) => <EmailRow key={r.email} result={r} />)}
            </div>
          )}

          {cleanResults.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-green">
                Clean ({cleanResults.length})
              </p>
              {cleanResults.map((r) => <EmailRow key={r.email} result={r} />)}
            </div>
          )}

          {errorResults.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-orange">
                Check Failed ({errorResults.length})
              </p>
              {errorResults.map((r) => <EmailRow key={r.email} result={r} />)}
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
