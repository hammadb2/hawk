"use client";

/**
 * Priority list #32 — first-login welcome / full scan report.
 *
 * PortalGate redirects the very first portal auth (``clients.last_portal_login_at IS NULL``)
 * here so the visitor sees their HAWK score, Insurance Readiness Score,
 * and every finding from the latest scan before the dashboard shell.
 * The "Continue to dashboard" CTA is gated on:
 *   - guarantee terms acceptance (inline banner)
 *   - company domain (inline banner, only when sign-up email is generic)
 *
 * All findings are grouped by severity; CRITICAL is expanded by default,
 * the rest collapse behind click-to-reveal headers.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { portalApi } from "@/lib/api";
import { needsCompanyDomainForMonitoring } from "@/lib/portal-domain";
import { Button } from "@/components/ui/button";
import { IncidentReportCard } from "@/components/portal/incident-report-card";
import { Input } from "@/components/ui/input";

type Finding = {
  id?: string;
  severity?: string;
  title?: string;
  description?: string;
};

type PortalProfile = {
  id: string;
  client_id: string;
  company_name: string | null;
  domain: string | null;
  guarantee_terms_accepted_at: string | null;
};

type ClientRow = {
  id: string;
  hawk_readiness_score: number | null;
  last_portal_login_at: string | null;
  prospect_id: string | null;
};

type ScanRow = {
  id: string;
  hawk_score: number | null;
  grade: string | null;
  findings: Record<string, unknown> | null;
  created_at: string;
};

const SEVERITY_ORDER = ["critical", "high", "medium", "warning", "low", "info", "ok"] as const;
type SeverityKey = (typeof SEVERITY_ORDER)[number];

const SEVERITY_LABEL: Record<SeverityKey, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  warning: "Medium",
  low: "Low",
  info: "Informational",
  ok: "Passing checks",
};

const SEVERITY_ACCENT: Record<SeverityKey, string> = {
  critical: "text-red border-red/40 bg-red/10",
  high: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  medium: "text-signal-600 border-signal/30 bg-signal/10",
  warning: "text-signal-600 border-signal/30 bg-signal/10",
  low: "text-ink-100 border-white/10 bg-white/5",
  info: "text-ink-200 border-white/10 bg-white/5",
  ok: "text-signal-400 border-signal/20 bg-signal/5",
};

function normalizeSeverity(s: string | undefined): SeverityKey {
  const v = (s || "").toLowerCase();
  return (SEVERITY_ORDER as readonly string[]).includes(v) ? (v as SeverityKey) : "medium";
}

function findingsFromScanPayload(findings: Record<string, unknown> | null | undefined): Finding[] {
  if (!findings || typeof findings !== "object") return [];
  const inner = (findings as Record<string, unknown>).findings;
  if (!Array.isArray(inner)) return [];
  return inner.filter((x): x is Finding => x !== null && typeof x === "object");
}

function ringColorForScore(score: number): string {
  if (score >= 85) return "#16a34a";
  if (score >= 70) return "#d97706";
  return "#dc2626";
}

/** Grouped buckets in severity order with their expanded/collapsed state. */
function groupFindings(findings: Finding[]): Record<SeverityKey, Finding[]> {
  const buckets: Record<SeverityKey, Finding[]> = {
    critical: [],
    high: [],
    medium: [],
    warning: [],
    low: [],
    info: [],
    ok: [],
  };
  for (const f of findings) buckets[normalizeSeverity(f.severity)].push(f);
  return buckets;
}

/** Compact score ring + numeric readout reused for HAWK + Insurance Readiness. */
function ScoreRing({ score, label, sub }: { score: number; label: string; sub?: string }) {
  const pct = Math.min(100, Math.max(0, score));
  const stroke = ringColorForScore(pct);
  return (
    <div className="flex flex-col items-center gap-2">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-200">{label}</p>
      <div className="relative h-32 w-32">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke={stroke}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${(pct / 100) * 264} 264`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold tabular-nums text-ink-0">{pct}</span>
          <span className="text-xs text-ink-200">/ 100</span>
        </div>
      </div>
      {sub ? <p className="text-xs text-ink-200">{sub}</p> : null}
    </div>
  );
}

function SeveritySection({
  sev,
  findings,
  defaultOpen,
}: {
  sev: SeverityKey;
  findings: Finding[];
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (findings.length === 0) return null;
  const accent = SEVERITY_ACCENT[sev];
  return (
    <section className={`rounded-xl border ${accent} overflow-hidden`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold uppercase tracking-wide">{SEVERITY_LABEL[sev]}</span>
          <span className="rounded-full bg-black/30 px-2 py-0.5 text-xs font-medium tabular-nums text-ink-0">
            {findings.length}
          </span>
        </div>
        <span className="text-xs text-ink-200">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <ul className="divide-y divide-white/5 bg-ink-900/60">
          {findings.map((f, i) => (
            <li key={f.id || `${sev}-${i}`} className="px-4 py-3">
              <p className="text-sm font-medium text-ink-0">{f.title || "Untitled finding"}</p>
              {f.description ? (
                <p className="mt-1 text-sm leading-relaxed text-ink-200">{f.description}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export default function PortalWelcomePage() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [portalProfile, setPortalProfile] = useState<PortalProfile | null>(null);
  const [client, setClient] = useState<ClientRow | null>(null);
  const [scan, setScan] = useState<ScanRow | null>(null);
  const [userEmail, setUserEmail] = useState("");
  const [acceptBusy, setAcceptBusy] = useState(false);
  const [domainInput, setDomainInput] = useState("");
  const [domainBusy, setDomainBusy] = useState(false);
  const [domainError, setDomainError] = useState("");
  const markedSeenRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      router.replace("/portal/login?next=/portal/welcome");
      return;
    }
    setUserEmail((user.email || "").trim().toLowerCase());

    const { data: cpp } = await supabase
      .from("client_portal_profiles")
      .select("id,client_id,company_name,domain,guarantee_terms_accepted_at")
      .eq("user_id", user.id)
      .maybeSingle();

    if (!cpp) {
      setPortalProfile(null);
      setClient(null);
      setScan(null);
      setLoading(false);
      return;
    }
    setPortalProfile(cpp as PortalProfile);

    const { data: cl } = await supabase
      .from("clients")
      .select("id,hawk_readiness_score,last_portal_login_at,prospect_id")
      .eq("id", cpp.client_id)
      .single();
    setClient((cl as ClientRow) ?? null);

    const pid = (cl as ClientRow | null)?.prospect_id ?? null;
    if (pid) {
      const { data: scans } = await supabase
        .from("crm_prospect_scans")
        .select("id,hawk_score,grade,findings,created_at")
        .eq("prospect_id", pid)
        .order("created_at", { ascending: false })
        .limit(1);
      setScan((scans?.[0] as ScanRow) ?? null);
    } else {
      setScan(null);
    }

    setLoading(false);
  }, [router, supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  // Fire-and-forget mark-first-login-seen after the page renders — the CTA
  // intentionally still works even if this fails; worst case PortalGate
  // redirects here once more on next login.
  useEffect(() => {
    if (loading || markedSeenRef.current || !client) return;
    if (client.last_portal_login_at) return;
    markedSeenRef.current = true;
    void (async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) return;
      try {
        await portalApi.markFirstLoginSeen(session.access_token);
      } catch (e) {
        console.error("portal mark-first-login-seen:", e);
      }
    })();
  }, [loading, client, supabase]);

  async function acceptGuaranteeSummary() {
    if (!portalProfile) return;
    setAcceptBusy(true);
    try {
      const { error } = await supabase
        .from("client_portal_profiles")
        .update({ guarantee_terms_accepted_at: new Date().toISOString() })
        .eq("id", portalProfile.id);
      if (error) {
        toast.error("Could not save acceptance. Try again or contact support.");
        return;
      }
      setPortalProfile((p) =>
        p ? { ...p, guarantee_terms_accepted_at: new Date().toISOString() } : p,
      );
    } finally {
      setAcceptBusy(false);
    }
  }

  async function submitPrimaryDomain() {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.access_token) {
      toast.error("Sign in again to continue.");
      return;
    }
    setDomainBusy(true);
    setDomainError("");
    try {
      const saved = await portalApi.setPrimaryDomain({ domain: domainInput.trim() }, session.access_token);
      setPortalProfile((p) => (p ? { ...p, domain: saved.domain } : p));
      setDomainInput("");
      toast.success("Domain saved — we’ll use it for monitoring and security scans.");
    } catch (e) {
      setDomainError(e instanceof Error ? e.message : "Could not save domain.");
    } finally {
      setDomainBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-ink-200">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
      </div>
    );
  }

  if (!portalProfile || !client) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-signal/30 bg-signal/10/90 p-6 text-sm text-signal-800">
        <p className="font-medium text-signal-700">No client portal is linked to this account yet.</p>
        <p className="mt-2 text-ink-200">
          After your first HAWK subscription checkout, we&apos;ll email you a magic link. If you believe this is an error,
          contact your CSM.
        </p>
        <Button asChild className="mt-4 bg-signal text-white">
          <Link href="/portal/login">Back to login</Link>
        </Button>
      </div>
    );
  }

  const hawkScore = scan?.hawk_score ?? 0;
  const readiness = client.hawk_readiness_score ?? hawkScore;
  const grade = scan?.grade ?? "—";

  const findingsList = findingsFromScanPayload(scan?.findings ?? null);
  const buckets = groupFindings(findingsList);
  const totalFindings = findingsList.length;

  const needsGuarantee = !portalProfile.guarantee_terms_accepted_at;
  const needsDomain = needsCompanyDomainForMonitoring(userEmail, portalProfile.domain);
  const ctaDisabled = needsGuarantee || needsDomain;

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-signal-400">Welcome to HAWK</p>
        <h1 className="text-3xl font-semibold text-ink-0">
          {portalProfile.company_name ?? portalProfile.domain ?? "Your organization"}
        </h1>
        <p className="text-sm text-ink-200">
          Your latest scan summary and every finding we pulled. Resolve critical &amp; high items first; the dashboard
          unlocks once you accept the guarantee terms{needsDomain ? " and add your monitored domain" : ""}.
        </p>
      </header>

      <section className="rounded-2xl border border-white/10 bg-ink-800 p-6 shadow-sm">
        <div className="grid gap-6 sm:grid-cols-3 sm:items-center">
          <div className="flex flex-col items-center sm:items-start">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-200">Domain scanned</p>
            <p className="mt-1 max-w-full break-words text-lg font-semibold text-ink-0">
              {portalProfile.domain || "—"}
            </p>
            <p className="mt-1 text-xs text-ink-200">
              Grade <span className="font-medium text-ink-0">{grade}</span> · {totalFindings} total findings
            </p>
          </div>
          <div className="flex justify-center">
            <ScoreRing score={hawkScore} label="HAWK score" sub="Attack-surface visibility" />
          </div>
          <div className="flex justify-center sm:justify-end">
            <ScoreRing
              score={readiness}
              label="Insurance Readiness"
              sub="SLA-based — keep findings resolved"
            />
          </div>
        </div>
      </section>

      {needsGuarantee ? (
        <section className="rounded-xl border border-amber-400/40 bg-amber-400/5 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-amber-300">Breach response guarantee — review required</p>
              <p className="mt-1 text-sm leading-relaxed text-ink-200">
                HAWK Shield includes a financially backed breach response guarantee when you meet the conditions in
                your agreement. Critical &amp; high findings must be remediated within stated windows and incidents
                must be reported as required.{" "}
                <Link href="/guarantee-terms" className="font-medium text-signal hover:underline">
                  Read full terms
                </Link>
                .
              </p>
            </div>
            <Button
              type="button"
              disabled={acceptBusy}
              onClick={() => void acceptGuaranteeSummary()}
              className="shrink-0 bg-signal text-white hover:bg-signal-400"
            >
              {acceptBusy ? "Saving…" : "I understand and accept"}
            </Button>
          </div>
        </section>
      ) : null}

      {needsDomain ? (
        <section className="rounded-xl border border-signal/40 bg-signal/5 p-4">
          <div className="space-y-3">
            <div>
              <p className="text-sm font-semibold text-signal-300">Add your company domain</p>
              <p className="mt-1 text-sm leading-relaxed text-ink-200">
                You signed up with a generic email provider, so we don&apos;t know which site to monitor. Enter the
                main public domain (without{" "}
                <code className="text-ink-100">https://</code> or <code className="text-ink-100">www</code>) — for
                example <span className="text-ink-0">acme.com</span>.
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
              <Input
                type="text"
                autoComplete="off"
                placeholder="company.com"
                value={domainInput}
                onChange={(e) => setDomainInput(e.target.value)}
                className="border-white/10 bg-ink-800 text-ink-0 placeholder:text-ink-0 sm:max-w-sm"
              />
              <Button
                type="button"
                disabled={domainBusy || !domainInput.trim()}
                onClick={() => void submitPrimaryDomain()}
                className="bg-signal text-white hover:bg-signal-400"
              >
                {domainBusy ? "Saving…" : "Save domain"}
              </Button>
            </div>
            {domainError ? <p className="text-sm text-red">{domainError}</p> : null}
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-xl font-semibold text-ink-0">All findings</h2>
          <p className="text-xs text-ink-200">{totalFindings} total · sorted by severity</p>
        </div>
        {totalFindings === 0 ? (
          <p className="rounded-xl border border-white/10 bg-ink-800 p-4 text-sm text-ink-200">
            No findings yet. Your first scheduled scan runs automatically; you can also trigger a manual scan from
            Settings once you&apos;re inside the dashboard.
          </p>
        ) : (
          <div className="space-y-3">
            {SEVERITY_ORDER.map((sev) => (
              <SeveritySection
                key={sev}
                sev={sev}
                findings={buckets[sev]}
                defaultOpen={sev === "critical"}
              />
            ))}
          </div>
        )}
      </section>

      <section className="border-t border-white/10 pt-8">
        <IncidentReportCard />
      </section>

      <section className="flex flex-col items-center gap-3 border-t border-white/10 pt-8 text-center">
        <Button
          type="button"
          size="lg"
          className="bg-signal text-white hover:bg-signal-400 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={ctaDisabled}
          onClick={() => router.push("/portal")}
        >
          Continue to dashboard →
        </Button>
        {ctaDisabled ? (
          <p className="text-xs text-ink-200">
            {needsGuarantee && needsDomain
              ? "Accept the guarantee terms and add your domain to unlock the dashboard."
              : needsGuarantee
                ? "Accept the guarantee terms to unlock the dashboard."
                : "Add your monitored domain to unlock the dashboard."}
          </p>
        ) : (
          <p className="text-xs text-ink-200">You&apos;re all set — the full dashboard has Ask-HAWK, Findings, Benchmark, and more.</p>
        )}
      </section>
    </div>
  );
}
