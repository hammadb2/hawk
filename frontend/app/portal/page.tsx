"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import {
  findingsListFromScanPayload,
  summarizeSeverity,
  topFindingsPlainEnglish,
} from "@/lib/portal/findings-parse";
import { ReadinessSparkline } from "@/components/portal/readiness-sparkline";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type PortalProfile = {
  id: string;
  client_id: string;
  company_name: string | null;
  domain: string | null;
  guarantee_terms_accepted_at: string | null;
};

type ClientRow = {
  id: string;
  prospect_id: string | null;
  mrr_cents: number;
  onboarding_sequence_status: string | null;
  hawk_readiness_score: number | null;
  guarantee_status: string | null;
  certification_eligible_at: string | null;
  certified_at: string | null;
  guarantee_checklist_critical_ok: boolean | null;
  guarantee_checklist_high_ok: boolean | null;
  guarantee_checklist_subscription_ok: boolean | null;
};

type ScanRow = {
  id: string;
  hawk_score: number | null;
  grade: string | null;
  findings: Record<string, unknown> | null;
  created_at: string;
};

function PortalWelcomeToast() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const welcomeToast = useRef(false);
  const supabase = useMemo(() => createClient(), []);
  useEffect(() => {
    if (searchParams.get("welcome") !== "1") return;
    void (async () => {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      // Only toast after Stripe when already signed in — otherwise /portal redirects to login with ?welcome=1
      if (!user) return;
      if (welcomeToast.current) return;
      welcomeToast.current = true;
      const test = searchParams.get("test_checkout") === "1";
      toast.success(
        test
          ? "Test checkout complete — Stripe test mode. No real charge. Webhook should have fired; check CRM and email."
          : "Welcome to HAWK — your subscription is active. Check your email for onboarding.",
      );
      router.replace("/portal", { scroll: false });
    })();
  }, [searchParams, router, supabase]);
  return null;
}

function PortalHomeContent() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [portal, setPortal] = useState<PortalProfile | null>(null);
  const [client, setClient] = useState<ClientRow | null>(null);
  const [scan, setScan] = useState<ScanRow | null>(null);
  const [pipedaBusy, setPipedaBusy] = useState(false);
  const [remediation, setRemediation] = useState<{
    fixedThisMonth: number;
    inProgress: number;
    openTracked: number;
  } | null>(null);
  const [readinessHistory, setReadinessHistory] = useState<{ score: number; at: string }[]>([]);
  const [acceptBusy, setAcceptBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      const q = new URLSearchParams();
      q.set("next", "/portal");
      if (searchParams.get("welcome") === "1") q.set("welcome", "1");
      if (searchParams.get("test_checkout") === "1") q.set("test_checkout", "1");
      router.replace(`/portal/login?${q.toString()}`);
      setLoading(false);
      return;
    }

    const { data: cpp, error: e1 } = await supabase
      .from("client_portal_profiles")
      .select("id,client_id,company_name,domain,guarantee_terms_accepted_at")
      .eq("user_id", user.id)
      .maybeSingle();

    if (e1 || !cpp) {
      setPortal(null);
      setClient(null);
      setScan(null);
      setRemediation(null);
      setReadinessHistory([]);
      setLoading(false);
      return;
    }

    setPortal(cpp as PortalProfile);

    const { data: cl, error: e2 } = await supabase
      .from("clients")
      .select(
        "id,prospect_id,mrr_cents,onboarding_sequence_status,hawk_readiness_score,guarantee_status,certification_eligible_at,certified_at,guarantee_checklist_critical_ok,guarantee_checklist_high_ok,guarantee_checklist_subscription_ok",
      )
      .eq("id", cpp.client_id)
      .single();

    if (e2 || !cl) {
      setClient(null);
      setScan(null);
      setRemediation(null);
      setReadinessHistory([]);
      setLoading(false);
      return;
    }

    setClient(cl as ClientRow);

    const cid = cpp.client_id as string;
    const prospectId = cl.prospect_id as string | null;

    const [scansRes, stRes, evRes] = await Promise.all([
      prospectId
        ? supabase
            .from("crm_prospect_scans")
            .select("id,hawk_score,grade,findings,created_at")
            .eq("prospect_id", prospectId)
            .order("created_at", { ascending: false })
            .limit(1)
        : Promise.resolve({ data: null, error: null }),
      supabase.from("portal_finding_status").select("status,updated_at").eq("client_id", cid),
      supabase
        .from("hawk_guarantee_events")
        .select("readiness_score,created_at")
        .eq("client_id", cid)
        .not("readiness_score", "is", null)
        .order("created_at", { ascending: true })
        .limit(40),
    ]);

    setScan((scansRes.data?.[0] as ScanRow) ?? null);

    const monthStart = new Date();
    monthStart.setDate(1);
    monthStart.setHours(0, 0, 0, 0);
    const ms = monthStart.getTime();
    let fixedThisMonth = 0;
    let inProgress = 0;
    let openTracked = 0;
    for (const r of stRes.data || []) {
      const row = r as { status: string; updated_at: string };
      if (row.status === "in_progress") inProgress += 1;
      if (row.status === "open") openTracked += 1;
      if (row.status === "fixed") {
        const t = new Date(row.updated_at).getTime();
        if (!Number.isNaN(t) && t >= ms) fixedThisMonth += 1;
      }
    }
    setRemediation({ fixedThisMonth, inProgress, openTracked });

    const evRows = (evRes.data ?? []) as { readiness_score: number | null; created_at: string }[];
    setReadinessHistory(
      evRows
        .filter((r) => typeof r.readiness_score === "number")
        .map((r) => ({ score: r.readiness_score as number, at: r.created_at })),
    );

    setLoading(false);
  }, [router, supabase, searchParams]);

  useEffect(() => {
    void load();
  }, [load]);

  async function acceptGuaranteeSummary() {
    if (!portal) return;
    setAcceptBusy(true);
    try {
      const { error } = await supabase
        .from("client_portal_profiles")
        .update({ guarantee_terms_accepted_at: new Date().toISOString() })
        .eq("id", portal.id);
      if (error) {
        toast.error("Could not save acceptance. Try again or contact support.");
        return;
      }
      setPortal((p) => (p ? { ...p, guarantee_terms_accepted_at: new Date().toISOString() } : p));
      toast.success("Welcome to your HAWK dashboard.");
    } finally {
      setAcceptBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-700 border-t-[#00C48C]" />
      </div>
    );
  }

  if (!portal || !client) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-amber-500/30 bg-amber-500/5 p-6 text-sm text-amber-100">
        <p className="font-medium text-amber-50">No client portal is linked to this account yet.</p>
        <p className="mt-2 text-zinc-400">
          After your first HAWK subscription checkout, we&apos;ll email you a magic link. If you believe this is an error,
          contact your CSM.
        </p>
        <Button asChild className="mt-4 bg-[#00C48C] text-[#07060C]">
          <Link href="/portal/login">Back to login</Link>
        </Button>
      </div>
    );
  }

  const scanScore = scan?.hawk_score ?? 0;
  const readiness = client.hawk_readiness_score ?? scanScore;
  const grade = scan?.grade ?? "—";

  const guaranteeBadge =
    client.guarantee_status === "suspended"
      ? { label: "SUSPENDED", className: "bg-red-500/20 text-red-200 ring-red-500/40" }
      : client.guarantee_status === "at_risk"
        ? { label: "AT RISK", className: "bg-amber-500/20 text-amber-100 ring-amber-500/40" }
        : { label: "ACTIVE", className: "bg-emerald-500/15 text-emerald-200 ring-emerald-500/35" };

  let certLabel: "Earned" | "At Risk" | "Pending" = "Pending";
  if (client.certified_at) certLabel = "Earned";
  else if (
    client.guarantee_status === "at_risk" ||
    client.guarantee_status === "suspended" ||
    (typeof client.hawk_readiness_score === "number" && client.hawk_readiness_score < 85)
  ) {
    certLabel = "At Risk";
  }

  let daysUntilCert: number | null = null;
  if (client.certification_eligible_at && !client.certified_at) {
    const end = new Date(client.certification_eligible_at).getTime();
    const now = Date.now();
    daysUntilCert = Math.max(0, Math.ceil((end - now) / (86400 * 1000)));
  }

  const ringColor = readiness >= 85 ? "#16a34a" : readiness >= 70 ? "#d97706" : "#dc2626";
  const ringPct = Math.min(100, Math.max(0, readiness));
  const findingsRaw = scan?.findings;
  const list = findingsListFromScanPayload(
    findingsRaw && typeof findingsRaw === "object" ? (findingsRaw as Record<string, unknown>) : null,
  );
  const sev = summarizeSeverity(list);
  const topPlain = topFindingsPlainEnglish(list, 3);
  const criticalPreview =
    sev.criticalCount > 0
      ? `${sev.criticalCount} critical: ${sev.criticalTitles[0] ?? "see Findings"}${sev.criticalCount > 1 ? "…" : ""}`
      : sev.highCount > 0
        ? `${sev.highCount} high-severity finding(s) in the latest scan — open Findings to prioritize.`
        : null;

  const showGuaranteeGate = !portal.guarantee_terms_accepted_at;

  async function downloadPipedaPdf() {
    setPipedaBusy(true);
    try {
      const res = await fetch("/api/portal/pipeda-report");
      if (!res.ok) {
        const j = (await res.json().catch(() => ({}))) as { error?: string };
        window.alert(j.error || "Could not generate the report. Try again later.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "hawk-pipeda-overview.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      window.alert("Download failed. Check your connection and try again.");
    } finally {
      setPipedaBusy(false);
    }
  }

  const guaranteeDashboard = (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Breach response guarantee</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ring-1 ${guaranteeBadge.className}`}>
              {guaranteeBadge.label}
            </span>
            <span className="text-sm text-zinc-400">
              Certification: <span className="font-medium text-zinc-100">{certLabel}</span>
            </span>
          </div>
          {client.certification_eligible_at && !client.certified_at && daysUntilCert !== null && (
            <p className="mt-3 text-sm text-zinc-400">
              Days until HAWK Certified eligibility:{" "}
              <span className="font-semibold tabular-nums text-zinc-100">{daysUntilCert}</span>
            </p>
          )}
          {!client.certification_eligible_at && !client.certified_at && (
            <p className="mt-3 text-sm text-zinc-500">
              HAWK Certified countdown appears once your 90-day certification window is set (after Shield onboarding).
            </p>
          )}
          {client.certified_at && (
            <p className="mt-3 text-sm text-emerald-400/90">You are HAWK Certified — badge and certificate are available in your account.</p>
          )}
        </div>

        <div className="flex flex-col items-center gap-3">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">HAWK Readiness Score</p>
          <div className="relative h-36 w-36">
            <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="42" fill="none" stroke="rgb(39 39 42)" strokeWidth="10" />
              <circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke={ringColor}
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={`${(ringPct / 100) * 264} 264`}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold tabular-nums text-zinc-50">{readiness}</span>
              <span className="text-xs text-zinc-500">/ 100</span>
            </div>
          </div>
          <p className="max-w-[14rem] text-center text-xs text-zinc-500">
            SLA-based score — updated after each Shield scan. Keep critical &amp; high items within the window to stay
            certified.
          </p>
          {readinessHistory.length >= 2 && (
            <div className="w-full max-w-[14rem]">
              <ReadinessSparkline points={readinessHistory} />
            </div>
          )}
        </div>
      </div>

      <div className="mt-8 border-t border-zinc-800 pt-6">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Guarantee conditions</p>
        <ul className="mt-4 space-y-3">
          <li className="flex items-start gap-3 text-sm">
            <span className={client.guarantee_checklist_critical_ok !== false ? "text-emerald-400" : "text-red-400"}>
              {client.guarantee_checklist_critical_ok !== false ? "✓" : "✕"}
            </span>
            <span className="text-zinc-300">Critical findings resolved within 24–48 hours of notification</span>
          </li>
          <li className="flex items-start gap-3 text-sm">
            <span className={client.guarantee_checklist_high_ok !== false ? "text-emerald-400" : "text-red-400"}>
              {client.guarantee_checklist_high_ok !== false ? "✓" : "✕"}
            </span>
            <span className="text-zinc-300">High findings resolved within 48 hours</span>
          </li>
          <li className="flex items-start gap-3 text-sm">
            <span className={client.guarantee_checklist_subscription_ok !== false ? "text-emerald-400" : "text-red-400"}>
              {client.guarantee_checklist_subscription_ok !== false ? "✓" : "✕"}
            </span>
            <span className="text-zinc-300">Subscription active</span>
          </li>
        </ul>
      </div>

      <div className="mt-8 rounded-xl border border-rose-500/20 bg-rose-500/5 p-4">
        <h2 className="text-sm font-semibold text-rose-200">Top findings (plain English)</h2>
        {topPlain.length > 0 ? (
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-zinc-300">
            {topPlain.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ol>
        ) : (
          <p className="mt-2 text-sm text-zinc-400">
            {criticalPreview
              ? criticalPreview.slice(0, 320)
              : "No critical or high items in the latest scan payload. Open Findings for the full list."}
          </p>
        )}
        <Link href="/portal/findings" className="mt-2 inline-block text-xs font-medium text-[#00C48C] hover:underline">
          Open findings →
        </Link>
      </div>
    </section>
  );

  return (
    <div className="space-y-8">
      <Dialog open={showGuaranteeGate}>
        <DialogContent hideClose className="max-w-lg border-[#00C48C]/25 bg-[#0a0910] sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-xl text-zinc-50">Breach Response Guarantee</DialogTitle>
            <DialogDescription className="text-left text-sm leading-relaxed text-zinc-400">
              HAWK Shield includes a financially backed breach response guarantee when you meet the conditions in your
              agreement. Critical and high findings must be remediated within the stated windows, your subscription must
              stay active, and incidents must be reported as required. Review the{" "}
              <Link href="/guarantee-terms" className="font-medium text-[#00C48C] hover:underline">
                full guarantee terms
              </Link>{" "}
              for exclusions and limits.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              className="w-full bg-[#00C48C] text-[#07060C] hover:bg-[#00e6a8] sm:w-auto"
              disabled={acceptBusy}
              onClick={() => void acceptGuaranteeSummary()}
            >
              {acceptBusy ? "Saving…" : "I understand and accept"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">{portal.company_name ?? portal.domain ?? "Your organization"}</h1>
        <p className="text-sm text-zinc-500">{portal.domain}</p>
      </div>

      {guaranteeDashboard}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3">
        {[
          { href: "/portal/ask", label: "Ask HAWK AI", sub: "Claude + your scan context" },
          { href: "/portal/briefing", label: "Weekly briefing", sub: "Sector threat digest" },
          { href: "/portal/findings", label: "Findings", sub: "Status & verify fixes" },
          { href: "/portal/journey", label: "Journey", sub: "Scores & badges" },
          { href: "/portal/benchmark", label: "Benchmark", sub: "Peer comparison" },
          { href: "/portal/attack-paths", label: "Attack paths", sub: "Breach scenarios" },
          { href: "/portal/enterprise", label: "Enterprise", sub: "Multi-domain rollup" },
          { href: "/portal/attacker-simulation", label: "Attacker sim", sub: "Weekly narrative" },
          { href: "/portal/compliance", label: "C-27 primer", sub: "Canada privacy reform" },
        ].map((x) => (
          <Link
            key={x.href}
            href={x.href}
            className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 transition hover:border-[#00C48C]/40"
          >
            <p className="text-sm font-medium text-zinc-100">{x.label}</p>
            <p className="mt-1 text-xs text-zinc-500">{x.sub}</p>
          </Link>
        ))}
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 lg:col-span-1">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Attack surface score</p>
          <div className="mt-4 flex items-end gap-2">
            <span className="text-5xl font-bold tabular-nums text-[#00C48C]">{scanScore}</span>
            <span className="pb-2 text-2xl text-zinc-400">/100</span>
          </div>
          <p className="mt-2 text-sm text-zinc-400">
            Grade <span className="font-medium text-zinc-200">{grade}</span>
          </p>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 lg:col-span-2">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Monitoring</p>
          <ul className="mt-4 space-y-3 text-sm text-zinc-300">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-[#00C48C]" />
              Live surface monitoring active
            </li>
            <li>Onboarding: {client.onboarding_sequence_status ?? "—"}</li>
          </ul>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <h2 className="text-sm font-semibold text-emerald-200">Fixed this month</h2>
          <p className="mt-2 text-3xl font-semibold tabular-nums text-emerald-100">
            {remediation?.fixedThisMonth ?? 0}
          </p>
          <p className="mt-1 text-sm text-zinc-500">
            Items marked <strong className="text-zinc-400">fixed</strong> this calendar month.{" "}
            {remediation !== null && (
              <>
                In progress: {remediation.inProgress} · Open (tracked): {remediation.openTracked}.
              </>
            )}
          </p>
          <Link href="/portal/findings" className="mt-2 inline-block text-xs font-medium text-[#00C48C] hover:underline">
            Update status →
          </Link>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 className="text-sm font-semibold text-zinc-200">Reports</h2>
          <p className="mt-2 text-sm text-zinc-400">
            PIPEDA-oriented overview from your latest scan: which issues map to privacy duties, rough risk framing, and
            remediation themes.
          </p>
          <Button
            type="button"
            className="mt-3 bg-zinc-100 text-zinc-900 hover:bg-white"
            disabled={pipedaBusy || !scan}
            onClick={() => void downloadPipedaPdf()}
          >
            {pipedaBusy ? "Preparing PDF…" : "Download PIPEDA overview (PDF)"}
          </Button>
          {!scan && (
            <p className="mt-2 text-xs text-zinc-600">Run or complete a scan first — then this button enables.</p>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-zinc-800 bg-zinc-900/30 p-6">
        <h2 className="text-lg font-semibold text-zinc-100">Ask HAWK</h2>
        <p className="mt-2 text-sm text-zinc-500">
          Get personalised security Q&amp;A grounded in your latest scan context — open the full chat with streaming
          answers.
        </p>
        <Button asChild className="mt-4 bg-zinc-100 text-zinc-900 hover:bg-white">
          <Link href="/portal/ask">Open Ask HAWK</Link>
        </Button>
      </section>
    </div>
  );
}

export default function PortalHomePage() {
  return (
    <>
      <Suspense fallback={null}>
        <PortalWelcomeToast />
      </Suspense>
      <Suspense
        fallback={
          <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-700 border-t-[#00C48C]" />
          </div>
        }
      >
        <PortalHomeContent />
      </Suspense>
    </>
  );
}
