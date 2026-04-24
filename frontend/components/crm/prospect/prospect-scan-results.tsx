"use client";

import { useMemo, useState } from "react";
import { HawkScoreRing } from "@/components/crm/prospect/hawk-score-ring";
import type { CrmProspectScanRow } from "@/lib/crm/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";
import { crmDialogSurface, crmFieldSurface, crmSurfaceCard } from "@/lib/crm/crm-surface";

type ScanFinding = {
  id?: string;
  severity?: string;
  category?: string;
  title?: string;
  description?: string;
  interpretation?: string;
  fix_guide?: string;
  remediation?: string;
  layer?: string;
  verified_at?: string;
};

type AttackPath = {
  name?: string;
  steps?: string[];
  likelihood?: string;
  impact?: string;
};

function extractFindings(findingsJson: Record<string, unknown> | null): ScanFinding[] {
  if (!findingsJson || typeof findingsJson !== "object") return [];
  const raw = findingsJson as Record<string, unknown>;
  if (Array.isArray(raw.findings)) return raw.findings as ScanFinding[];
  return [];
}

function severityRank(s: string): number {
  const x = (s || "").toLowerCase();
  if (x === "critical") return 0;
  if (x === "high") return 1;
  if (x === "medium" || x === "warning") return 2;
  if (x === "low" || x === "info") return 3;
  if (x === "ok") return 5;
  return 4;
}

function severityBadgeClass(s: string): string {
  const x = (s || "").toLowerCase();
  if (x === "critical") return "bg-red/15 text-white";
  if (x === "high") return "bg-orange-600/90 text-white";
  if (x === "medium" || x === "warning") return "bg-amber-600/90 text-white";
  if (x === "low" || x === "info") return "bg-ink-700 text-ink-0";
  if (x === "ok") return "bg-signal-600/90 text-white";
  return "bg-ink-600 text-ink-0";
}

function formatMoneyUsd(n: number): string {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function objectionTemplates(industry: string | null): { objection: string; response: string }[] {
  const t = (industry || "").toLowerCase();
  const isHealth = /dental|medical|health|clinic|hospital/.test(t);
  const isLegal = /legal|law|attorney/.test(t);
  const isFin = /financial|bank|wealth|invest|accounting|cpa/.test(t);
  if (isHealth) {
    return [
      {
        objection: "Our patient data is already protected by our systems.",
        response:
          "Patient data lives in more than the EMR — email, portals, and staff devices are where most healthcare breaches start. HAWK shows what criminals can see from the outside before they ever touch your charting system.",
      },
      { objection: "We're too small to be a target.", response: "SMBs are the majority of ransomware victims because defenses are lighter. Automated scans find you the same way they find enterprises — size doesn't matter to a bot." },
      { objection: "This sounds expensive for what we get.", response: "Compare to one privacy incident: PIPEDA notification, downtime, and reputation damage typically dwarf preventive monitoring. Starter is $199/mo to see value before Shield." },
    ];
  }
  if (isLegal) {
    return [
      {
        objection: "Solicitor–client privilege protects our communications.",
        response:
          "Privilege protects certain communications legally — it does not stop exposed email, weak passwords, or stolen credentials from being abused technically. HAWK shows the attack surface that can bypass policy controls.",
      },
      { objection: "Our firm uses a managed IT provider.", response: "Great — HAWK is an independent outside-in view. Many firms use us to validate MSP coverage and catch gaps in DNS, certificates, and third-party exposure." },
      { objection: "We don't have time for another tool.", response: "Reports are plain English with fix guides — built so partners can forward tasks to IT in minutes, not hours." },
    ];
  }
  if (isFin) {
    return [
      {
        objection: "We're already meeting regulatory requirements.",
        response:
          "Regulators expect reasonable safeguards — not just paperwork. HAWK shows live exposure (email, credentials, perimeter) that compliance reviews and point-in-time audits often miss between cycles.",
      },
      { objection: "Clients trust us already.", response: "Trust is easier when you can show a verified score and ongoing monitoring — especially for wealth and mortgage data." },
      { objection: "Is this going to flag false alarms?", response: "We severity-rank findings and explain impact in plain English so you focus on what actually increases breach risk." },
    ];
  }
  return [
    { objection: "We're too small for hackers to care.", response: "Most attacks are automated. If your domain or remote access is exposed, you're in the same pool as everyone else on the internet." },
    { objection: "We have antivirus and backups.", response: "Those help after something lands — HAWK reduces how easily attackers get in via exposed services, email security, and stolen passwords." },
    { objection: "We don't have an IT team.", response: "That's why fix guides are step-by-step in plain English — your staff or contractor can execute without security jargon." },
  ];
}

function passingHighlights(findings: ScanFinding[]): string[] {
  const sevs = new Set(findings.map((f) => (f.severity || "").toLowerCase()));
  const out: string[] = [];
  if (!sevs.has("critical")) out.push("No critical-severity exposures flagged in this pass.");
  if (!sevs.has("high")) out.push("No high-severity exposures flagged in this pass.");
  const hasEmail = findings.some((f) => (f.layer || "").includes("email") || (f.category || "").toLowerCase().includes("dmarc"));
  if (!hasEmail) out.push("Email authentication stack reviewed as part of scan pipeline.");
  if (out.length < 2) out.push("External attack surface enumerated (subdomains, ports, web fingerprints).");
  return out.slice(0, 5);
}

export function ProspectScanResultsPanel({
  scan,
  scanId,
  prospectId,
  companyName: _companyName,
  domain,
  industry,
  onVerified,
}: {
  scan: CrmProspectScanRow;
  scanId: string;
  prospectId: string;
  companyName: string | null;
  domain: string;
  industry: string | null;
  onVerified?: () => void;
}) {
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideText, setGuideText] = useState("");
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  const score = scan.hawk_score ?? 0;
  const findings = useMemo(() => extractFindings(scan.findings), [scan.findings]);
  const interpreted = useMemo(() => {
    const raw = scan.interpreted_findings;
    return Array.isArray(raw) ? (raw as Record<string, unknown>[]) : [];
  }, [scan.interpreted_findings]);

  const merged = useMemo(() => {
    const byId = new Map<string, Record<string, unknown>>();
    for (const row of interpreted) {
      const id = String(row.id ?? "");
      if (id) byId.set(id, row);
    }
    return findings.map((f, idx) => {
      const id = String(f.id ?? "");
      let interp = id ? byId.get(id) : undefined;
      if (
        !interp &&
        interpreted.length > 0 &&
        interpreted.length === findings.length &&
        interpreted[idx]
      ) {
        interp = interpreted[idx] as Record<string, unknown>;
      }
      const plain =
        (interp?.plain_english as string) ||
        (interp?.plainEnglish as string) ||
        f.interpretation ||
        f.description;
      const fix = (interp?.fix_guide as string) || (interp?.fixGuide as string) || f.fix_guide;
      return { ...f, interpretation: plain, fix_guide: fix };
    });
  }, [findings, interpreted]);

  const sorted = useMemo(
    () => [...merged].sort((a, b) => severityRank(String(a.severity)) - severityRank(String(b.severity))),
    [merged],
  );

  const criticalHigh = sorted.filter((f) => {
    const s = (f.severity || "").toLowerCase();
    return s === "critical" || s === "high";
  });
  const medLow = sorted.filter((f) => {
    const s = (f.severity || "").toLowerCase();
    return s === "medium" || s === "warning" || s === "low" || s === "info";
  });
  const okFindings = sorted.filter((f) => (f.severity || "").toLowerCase() === "ok");

  const breach = scan.breach_cost_estimate as Record<string, unknown> | null | undefined;
  const baselineUsd =
    typeof breach?.baseline_usd === "number"
      ? breach.baseline_usd
      : typeof breach?.baseline_usd === "string"
        ? parseInt(breach.baseline_usd, 10)
        : null;

  const topTitle =
    criticalHigh[0]?.title || medLow[0]?.title || sorted[0]?.title || "several exposure areas";
  const gradeLabel = scan.grade ?? "—";
  const openingLine = `I ran a scan on ${domain} and found ${topTitle}. Your score is ${score}/100 — Grade ${gradeLabel}.`;

  const objections = objectionTemplates(industry);
  const topObjection = objections[0];

  const attackPaths = useMemo((): AttackPath[] => {
    const raw = scan.attack_paths;
    if (!Array.isArray(raw)) return [];
    return raw.filter((x): x is AttackPath => x != null && typeof x === "object");
  }, [scan.attack_paths]);

  async function verifyFinding(f: ScanFinding) {
    const fid = f.id;
    if (!fid) {
      toast.error("Finding has no id — run a new scan.");
      return;
    }
    setVerifyingId(fid);
    try {
      const res = await fetch("/api/crm/finding-verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prospectId, scanId, findingId: fid }),
      });
      const j = (await res.json().catch(() => ({}))) as {
        verified?: boolean;
        message?: string;
        error?: string;
        detail?: string;
      };
      if (!res.ok) {
        toast.error([j.error, j.detail].filter(Boolean).join(" — ") || "Verify failed");
        return;
      }
      if (j.verified) {
        toast.success(j.message || "Marked verified — exposure not seen on rescan.");
        onVerified?.();
      } else {
        toast(j.message || "Still present — keep working the fix guide.", { icon: "ℹ️" });
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Verify request failed");
    } finally {
      setVerifyingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-6">
        <div className="flex flex-col items-center gap-1">
          <HawkScoreRing score={score} size={120} showEmptyState={false} />
          <div className="text-center">
            <div className="text-2xl font-bold text-ink-0">{scan.grade ?? "—"}</div>
            <div className="text-xs text-ink-200">{new Date(scan.created_at).toLocaleString()}</div>
            {scan.scan_version && (
              <div className="text-[10px] text-ink-0">Scanner v{scan.scan_version}</div>
            )}
          </div>
        </div>
        <div className="min-w-0 flex-1 space-y-1 text-sm text-ink-200">
          <p>
            <span className="text-ink-200">Industry:</span> {industry || "—"}
          </p>
          {breach?.summary != null && typeof breach.summary === "string" && (
            <p className="text-ink-100">{breach.summary}</p>
          )}
        </div>
      </div>

      {attackPaths.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-signal/90">Attack paths</h3>
          <div className="space-y-5">
            {attackPaths.map((p, pi) => (
              <div
                key={pi}
                className="rounded-lg border border-signal/30/40 bg-ink-800/20 px-3 py-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-signal-100">{p.name || `Path ${pi + 1}`}</span>
                  {p.likelihood && (
                    <span className="rounded bg-ink-800 px-2 py-0.5 text-[10px] uppercase text-ink-100">
                      {p.likelihood} likelihood
                    </span>
                  )}
                </div>
                {p.impact && <p className="mt-2 text-sm text-ink-200">{p.impact}</p>}
                {p.steps && p.steps.length > 0 && (
                  <div className="mt-3 flex flex-wrap items-start gap-1 text-xs text-ink-100">
                    {p.steps.map((step, si) => (
                      <div key={si} className="flex items-center gap-1">
                        {si > 0 && (
                          <span className="px-1 text-signal" aria-hidden>
                            →
                          </span>
                        )}
                        <span className="rounded-md border border-white/10 bg-ink-800 px-2 py-1">{step}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {criticalHigh.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-red/90">Critical & high</h3>
          <ul className="space-y-3">
            {criticalHigh.map((f, i) => (
              <li
                key={f.id || `ch-${i}`}
                className="rounded-lg border border-red/30 bg-red/15 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded px-2 py-0.5 text-[10px] font-semibold uppercase", severityBadgeClass(String(f.severity)))}>
                    {f.severity || "unknown"}
                  </span>
                  <span className="font-medium text-ink-0">{f.title || "Finding"}</span>
                  {f.verified_at && (
                    <span className="rounded bg-signal/10 px-2 py-0.5 text-[10px] text-signal-400">Verified</span>
                  )}
                </div>
                <p className="mt-1 text-sm text-ink-100">
                  {f.interpretation || f.description || "—"}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="border-white/15 text-ink-0"
                    disabled={!f.fix_guide && !f.remediation}
                    onClick={() => {
                      const text = (f.fix_guide || f.remediation || "").trim();
                      if (!text) {
                        toast.error("No fix guide for this finding yet.");
                        return;
                      }
                      setGuideText(text);
                      setGuideOpen(true);
                    }}
                  >
                    Fix guide
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="bg-ink-800 text-ink-0"
                    disabled={!f.id || !!f.verified_at || verifyingId === f.id}
                    title="Re-scans the domain; marks verified if this exposure no longer appears at the same severity."
                    onClick={() => void verifyFinding(f)}
                  >
                    {verifyingId === f.id ? "Checking…" : "Verify fix"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {medLow.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-signal/90">Medium & low</h3>
          <ul className="space-y-2">
            {medLow.map((f, i) => (
              <li key={f.id || `ml-${i}`} className={`px-3 py-2 ${crmFieldSurface}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded px-2 py-0.5 text-[10px] font-semibold uppercase", severityBadgeClass(String(f.severity)))}>
                    {f.severity || "unknown"}
                  </span>
                  <span className="text-sm font-medium text-ink-100">{f.title || "Finding"}</span>
                </div>
                <p className="mt-1 text-xs text-ink-200">{f.interpretation || f.description || "—"}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(f.fix_guide || f.remediation) && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs text-signal"
                      onClick={() => {
                        setGuideText(String(f.fix_guide || f.remediation));
                        setGuideOpen(true);
                      }}
                    >
                      Fix guide
                    </Button>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs text-ink-200"
                    disabled={!f.id || !!f.verified_at || verifyingId === f.id}
                    onClick={() => void verifyFinding(f)}
                  >
                    {verifyingId === f.id ? "Checking…" : "Verify fix"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(okFindings.length > 0 || sorted.length > 0) && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-signal/90">What&apos;s passing</h3>
          <ul className="space-y-1 text-sm text-ink-100">
            {okFindings.map((f, i) => (
              <li key={f.id || `ok-${i}`} className="flex gap-2">
                <span className="text-signal">✓</span>
                <span>{f.title || f.description || "Check passed"}</span>
              </li>
            ))}
            {passingHighlights(sorted).map((line, i) => (
              <li key={`ph-${i}`} className="flex gap-2">
                <span className="text-signal">✓</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={`p-4 ${crmSurfaceCard}`}>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-signal">Closer prep</h3>
        <div className="space-y-4 text-sm text-ink-100">
          <div>
            <div className="text-xs font-medium text-ink-0">Opening line</div>
            <p className="mt-1 text-white">&quot;{openingLine}&quot;</p>
          </div>
          {baselineUsd != null && !Number.isNaN(baselineUsd) && (
            <div className="rounded-lg border border-signal/30 bg-ink-800/25 px-3 py-2">
              <p className="text-sm font-medium text-amber-200">
                Estimated breach cost for a business like yours:{" "}
                <span className="text-signal-200">{formatMoneyUsd(baselineUsd)}</span>
                <span className="font-normal text-ink-200">
                  {" "}
                  — source: IBM 2025 Cost of Data Breach Report
                </span>
              </p>
            </div>
          )}
          <div>
            <div className="text-xs font-medium text-ink-0">
              Top objection ({industry || "general SMB"})
            </div>
            <p className="mt-2 text-ink-100">
              <span className="font-medium text-white">{topObjection.objection}</span>
            </p>
            <p className="mt-1 text-ink-200">{topObjection.response}</p>
          </div>
          {objections.length > 1 && (
            <div>
              <div className="text-xs font-medium text-ink-0">More objections</div>
              <ol className="mt-2 list-decimal space-y-2 pl-4 text-ink-200">
                {objections.slice(1).map((o, i) => (
                  <li key={i}>
                    <span className="font-medium text-ink-100">{o.objection}</span>
                    <span className="text-ink-0"> — </span>
                    {o.response}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </section>

      <Dialog open={guideOpen} onOpenChange={setGuideOpen}>
        <DialogContent className={`max-h-[85vh] overflow-y-auto ${crmDialogSurface}`}>
          <DialogHeader>
            <DialogTitle className="text-white">Fix guide</DialogTitle>
          </DialogHeader>
          <pre className="whitespace-pre-wrap font-sans text-sm text-ink-100">{guideText}</pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
