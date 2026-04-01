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
  if (x === "critical") return "bg-red-600/90 text-white";
  if (x === "high") return "bg-orange-600/90 text-white";
  if (x === "medium" || x === "warning") return "bg-amber-600/90 text-white";
  if (x === "low" || x === "info") return "bg-zinc-600 text-zinc-100";
  if (x === "ok") return "bg-emerald-700/90 text-white";
  return "bg-zinc-700 text-zinc-200";
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
      { objection: "We already have IT / our EMR vendor handles security.", response: "Vendors secure their product — not your email domain, exposed ports, or stolen passwords in breaches. HAWK looks at what attackers see from the outside, where most clinics get hit first." },
      { objection: "We're too small to be a target.", response: "SMBs are the majority of ransomware victims because defenses are lighter. Automated scans find you the same way they find enterprises — size doesn't matter to a bot." },
      { objection: "This sounds expensive for what we get.", response: "Compare to one privacy incident: PIPEDA notification, downtime, and reputation damage typically dwarf preventive monitoring. Starter is $199/mo to see value before Shield." },
    ];
  }
  if (isLegal) {
    return [
      { objection: "Client confidentiality is already covered by our processes.", response: "Processes help — but exposed services and weak email auth are what breach confidentiality technically. We show exactly what's visible to an attacker today." },
      { objection: "Our firm uses a managed IT provider.", response: "Great — HAWK is an independent outside-in view. Many firms use us to validate MSP coverage and catch gaps in DNS, certificates, and third-party exposure." },
      { objection: "We don't have time for another tool.", response: "Reports are plain English with fix guides — built so partners can forward tasks to IT in minutes, not hours." },
    ];
  }
  if (isFin) {
    return [
      { objection: "We're already regulated / audited.", response: "Compliance checks a point in time; HAWK monitors what changes week to week — new open ports, leaked creds, and misconfigurations that audits can miss between cycles." },
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
  companyName,
  domain,
  industry,
}: {
  scan: CrmProspectScanRow;
  companyName: string | null;
  domain: string;
  industry: string | null;
}) {
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideText, setGuideText] = useState("");

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
    return findings.map((f) => {
      const id = String(f.id ?? "");
      const interp = id ? byId.get(id) : undefined;
      const plain = (interp?.plain_english as string) || f.interpretation;
      const fix = (interp?.fix_guide as string) || f.fix_guide;
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

  const topTitle = criticalHigh[0]?.title || medLow[0]?.title || sorted[0]?.title || "several exposure areas";
  const who = (companyName || "").trim() || domain;
  const openingLine = `I ran a scan on ${who} (${domain}) and found ${topTitle.toLowerCase()} — their overall HAWK score is ${score}/100 (grade ${scan.grade ?? "—"}).`;

  const objections = objectionTemplates(industry);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-6">
        <div className="flex flex-col items-center gap-1">
          <HawkScoreRing score={score} size={120} />
          <div className="text-center">
            <div className="text-2xl font-bold text-zinc-100">{scan.grade ?? "—"}</div>
            <div className="text-xs text-zinc-500">{new Date(scan.created_at).toLocaleString()}</div>
            {scan.scan_version && (
              <div className="text-[10px] text-zinc-600">Scanner v{scan.scan_version}</div>
            )}
          </div>
        </div>
        <div className="min-w-0 flex-1 space-y-1 text-sm text-zinc-400">
          <p>
            <span className="text-zinc-500">Industry:</span> {industry || "—"}
          </p>
          {breach?.summary != null && typeof breach.summary === "string" && (
            <p className="text-zinc-300">{breach.summary}</p>
          )}
          {baselineUsd != null && !Number.isNaN(baselineUsd) && (
            <p className="text-zinc-200">
              Estimated breach cost context: sector-style average around{" "}
              <span className="font-semibold text-amber-200/90">{formatMoneyUsd(baselineUsd)}</span> USD (illustrative).
            </p>
          )}
        </div>
      </div>

      {criticalHigh.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-red-400/90">Critical & high</h3>
          <ul className="space-y-3">
            {criticalHigh.map((f, i) => (
              <li
                key={f.id || `ch-${i}`}
                className="rounded-lg border border-red-900/40 bg-red-950/20 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded px-2 py-0.5 text-[10px] font-semibold uppercase", severityBadgeClass(String(f.severity)))}>
                    {f.severity || "unknown"}
                  </span>
                  <span className="font-medium text-zinc-100">{f.title || "Finding"}</span>
                </div>
                <p className="mt-1 text-sm text-zinc-300">
                  {f.interpretation || f.description || "—"}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="border-zinc-600 text-zinc-200"
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
                    className="bg-zinc-800 text-zinc-400"
                    disabled
                    title="Micro-rescan per finding — shipping next"
                  >
                    Verify fix
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {medLow.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-amber-500/90">Medium & low</h3>
          <ul className="space-y-2">
            {medLow.map((f, i) => (
              <li
                key={f.id || `ml-${i}`}
                className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded px-2 py-0.5 text-[10px] font-semibold uppercase", severityBadgeClass(String(f.severity)))}>
                    {f.severity || "unknown"}
                  </span>
                  <span className="text-sm font-medium text-zinc-200">{f.title || "Finding"}</span>
                </div>
                <p className="mt-1 text-xs text-zinc-400">{f.interpretation || f.description || "—"}</p>
                {(f.fix_guide || f.remediation) && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="mt-1 h-7 px-2 text-xs text-emerald-400"
                    onClick={() => {
                      setGuideText(String(f.fix_guide || f.remediation));
                      setGuideOpen(true);
                    }}
                  >
                    Fix guide
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(okFindings.length > 0 || sorted.length > 0) && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-emerald-500/90">What&apos;s passing</h3>
          <ul className="space-y-1 text-sm text-zinc-300">
            {okFindings.map((f, i) => (
              <li key={f.id || `ok-${i}`} className="flex gap-2">
                <span className="text-emerald-500">✓</span>
                <span>{f.title || f.description || "Check passed"}</span>
              </li>
            ))}
            {passingHighlights(sorted).map((line, i) => (
              <li key={`ph-${i}`} className="flex gap-2">
                <span className="text-emerald-500">✓</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-teal-400/90">Closer prep</h3>
        <div className="space-y-3 text-sm text-zinc-300">
          <div>
            <div className="text-xs font-medium text-zinc-500">Opening line</div>
            <p className="mt-1 text-zinc-200">&quot;{openingLine}&quot;</p>
          </div>
          <div>
            <div className="text-xs font-medium text-zinc-500">Top objections ({industry || "general SMB"})</div>
            <ol className="mt-2 list-decimal space-y-2 pl-4">
              {objections.map((o, i) => (
                <li key={i} className="text-zinc-300">
                  <span className="font-medium text-zinc-200">{o.objection}</span>
                  <span className="text-zinc-500"> — </span>
                  {o.response}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <Dialog open={guideOpen} onOpenChange={setGuideOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto border-zinc-800 bg-zinc-950 text-zinc-100">
          <DialogHeader>
            <DialogTitle>Fix guide</DialogTitle>
          </DialogHeader>
          <pre className="whitespace-pre-wrap font-sans text-sm text-zinc-300">{guideText}</pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
