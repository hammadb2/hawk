"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { HawkScoreRing } from "@/components/crm/prospect/hawk-score-ring";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { CrmProspectScanRow, Prospect } from "@/lib/crm/types";
import { crmDialogSurface, crmSurfaceCard } from "@/lib/crm/crm-surface";

const PHASES = [
  "Checking subdomains…",
  "Scanning ports…",
  "Testing vulnerabilities…",
  "Checking breach databases…",
  "Generating AI analysis…",
];

const OBJECTIONS: Record<string, { q: string; a: string }[]> = {
  default: [
    { q: "We already have IT.", a: "This scan is external, like an attacker. It often finds gaps internal tools miss." },
    { q: "Send info by email.", a: "Happy to. The report is ready; I can send it right after this call." },
    { q: "We're too small to be targeted.", a: "Actually, 43% of cyberattacks target small businesses. Hackers use automated tools that scan every domain regardless of size." },
    { q: "How much does it cost?", a: "We have plans starting at $97/month. But first, let me show you what's exposed — the scan is free." },
  ],
  dental: [
    { q: "We use a managed IT vendor.", a: "Great. This shows what shows up from the outside on your domain, vendor aside." },
    { q: "We're PHIPA compliant already.", a: "PHIPA covers internal processes, but external attack surface is different. This scan checks what a hacker sees from outside." },
    { q: "Our patient data is in the cloud.", a: "Cloud apps still connect through your domain. If your email or DNS is compromised, patient data is at risk regardless of where it's stored." },
  ],
  law: [
    { q: "We have solicitor-client privilege concerns.", a: "Exactly why this matters — a breach of privileged communications is a regulatory nightmare. This scan shows external exposure, no data access needed." },
    { q: "Our IT firm handles security.", a: "They handle internal. This scan shows what's visible externally — things your IT firm may not monitor from outside the firewall." },
    { q: "We're a small firm, not a target.", a: "Law firms hold high-value data — client financials, case strategies. Attackers know this. 25% of law firms report being breached." },
  ],
  accounting: [
    { q: "We use QuickBooks Online, it's secure.", a: "QuickBooks itself may be, but your domain, email, and login portals are separate attack surfaces. That's what we scan." },
    { q: "CRA already audits us.", a: "CRA audits your books, not your cybersecurity. If client SINs or financial data leak, that's a privacy breach — different liability entirely." },
    { q: "Tax season is too busy for this.", a: "That's actually when you're most vulnerable — staff are rushing, phishing emails spike. A quick scan now prevents a crisis during crunch time." },
  ],
  financial: [
    { q: "We're regulated by IIROC/MFDA.", a: "Regulation requires you to protect client data, but doesn't tell you what's exposed externally. This scan fills that gap." },
    { q: "Our compliance team handles this.", a: "Compliance ensures policy — this scan shows technical reality. We often find gaps between what policy says and what's actually exposed." },
    { q: "Our clients trust us already.", a: "Trust is built on protection. If a breach hits the news, clients leave. This scan helps you verify the trust is warranted." },
  ],
  medical: [
    { q: "We're PHIPA/PIPEDA compliant.", a: "Compliance is about process. This scan shows technical exposure — open ports, vulnerable services, leaked credentials. Compliance doesn't catch those." },
    { q: "Our EMR vendor handles security.", a: "They secure their platform, but your clinic's domain, email, and network are your responsibility. That's what we check." },
    { q: "We don't store data on our servers.", a: "Your email, patient portal login, and DNS records are still on your domain. If those are compromised, attackers can intercept or redirect patient data." },
  ],
  optometry: [
    { q: "We're a small clinic.", a: "Small clinics are prime targets — less security budget, same valuable patient data. Automated attacks don't discriminate by size." },
    { q: "Our PMS vendor handles everything.", a: "Your practice management system is one piece. Your domain, email, and any connected devices are separate attack surfaces we scan." },
    { q: "Insurance covers us for breaches.", a: "Insurance covers costs after a breach, but not reputation damage or patient trust. Prevention is cheaper than a claim — and some policies require proof of security measures." },
  ],
  physiotherapy: [
    { q: "We mostly use paper records.", a: "If you have email, a website, or any online booking, you have an attack surface. We scan what's visible from the outside." },
    { q: "Our patients wouldn't care about a breach.", a: "Patient health records are worth 10x more than credit cards on the dark web. PHIPA requires you to protect them regardless." },
    { q: "We can't afford cybersecurity.", a: "The average breach costs a small health practice $150K+. Our plans start at $97/month — that's insurance for your digital front door." },
  ],
};

export default function CallModePage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";
  const supabase = useMemo(() => createClient(), []);
  const [briefOpen, setBriefOpen] = useState(true);
  const [entered, setEntered] = useState(false);
  const [p, setP] = useState<Prospect | null>(null);
  const [scan, setScan] = useState<CrmProspectScanRow | null>(null);
  const [scanning, setScanning] = useState(false);
  const [phaseIdx, setPhaseIdx] = useState(0);
  const [objIdx, setObjIdx] = useState(0);
  const [started, setStarted] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const load = useCallback(async () => {
    if (!id) return;
    const { data: prospect } = await supabase.from("prospects").select("*").eq("id", id).single();
    setP(prospect as Prospect);
    const { data: scans } = await supabase
      .from("crm_prospect_scans")
      .select("*")
      .eq("prospect_id", id)
      .order("created_at", { ascending: false })
      .limit(1);
    setScan((scans?.[0] as CrmProspectScanRow) ?? null);
  }, [id, supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!entered || started === null) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(t);
  }, [entered, started]);

  useEffect(() => {
    if (!entered) return;
    const onKey = (e: KeyboardEvent) => {
      const pool = OBJECTIONS[p?.industry?.toLowerCase().includes("dental") ? "dental" : "default"] ?? OBJECTIONS.default;
      if (e.key === "ArrowRight") setObjIdx((i) => Math.min(i + 1, pool.length - 1));
      if (e.key === "ArrowLeft") setObjIdx((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [entered, p?.industry]);

  async function runLiveScan() {
    if (!id) return;
    setScanning(true);
    setPhaseIdx(0);
    const tick = setInterval(() => setPhaseIdx((i) => Math.min(i + 1, PHASES.length - 1)), 8000);
    try {
      const res = await fetch("/api/crm/run-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prospectId: id }),
      });
      const j = (await res.json()) as { job_id?: string; error?: string };
      if (!res.ok || !j.job_id) {
        setScanning(false);
        clearInterval(tick);
        return;
      }
      let status = "";
      for (let i = 0; i < 120; i++) {
        const pr = await fetch(`/api/crm/scan-job/${encodeURIComponent(j.job_id)}`);
        const sj = await pr.json();
        status = (sj as { status?: string }).status || "";
        if (status === "complete") break;
        if (status === "failed") break;
        await new Promise((r) => setTimeout(r, 3000));
      }
      await fetch("/api/crm/run-scan/finalize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prospectId: id, jobId: j.job_id }),
      });
    } finally {
      clearInterval(tick);
      setScanning(false);
      void load();
    }
  }

  const rawFindings = scan?.findings;
  const topFindings: unknown[] =
    rawFindings &&
    typeof rawFindings === "object" &&
    Array.isArray((rawFindings as { findings?: unknown[] }).findings)
      ? (rawFindings as { findings: unknown[] }).findings.slice(0, 3)
      : Array.isArray(rawFindings)
        ? rawFindings.slice(0, 3)
        : [];
  const industryLower = (p?.industry ?? "").toLowerCase();
  const ind = industryLower.includes("dental") ? "dental"
    : industryLower.includes("law") || industryLower.includes("legal") ? "law"
    : industryLower.includes("accounting") || industryLower.includes("cpa") || industryLower.includes("bookkeep") ? "accounting"
    : industryLower.includes("financial") || industryLower.includes("advisor") || industryLower.includes("wealth") || industryLower.includes("insurance") ? "financial"
    : industryLower.includes("medical") || industryLower.includes("clinic") || industryLower.includes("doctor") || industryLower.includes("physician") ? "medical"
    : industryLower.includes("optom") || industryLower.includes("eye") || industryLower.includes("vision") ? "optometry"
    : industryLower.includes("physio") || industryLower.includes("chiro") || industryLower.includes("rehab") ? "physiotherapy"
    : "default";
  const pool = OBJECTIONS[ind] ?? OBJECTIONS.default;

  if (!id) return <p className="p-6 text-ink-200">Invalid</p>;

  return (
    <div className="min-h-screen bg-[#050508] text-ink-100">
      <Dialog open={briefOpen} onOpenChange={setBriefOpen}>
        <DialogContent className={crmDialogSurface}>
          <DialogHeader>
            <DialogTitle className="text-white">Pre-call brief</DialogTitle>
          </DialogHeader>
          <p className="text-sm leading-relaxed text-ink-100">
            Calling {p?.contact_name || "the prospect"} at {p?.company_name || p?.domain}
            <br />
            Score: {scan?.hawk_score ?? p?.hawk_score ?? "—"}/100 — Grade {(scan?.grade as string) || "—"}
            <br />
            Industry: {p?.industry || "—"}
          </p>
          <DialogFooter>
            <Button className="bg-signal-400" onClick={() => { setBriefOpen(false); setEntered(true); setStarted(Date.now()); }}>
              Enter call mode
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {entered && (
        <div className="flex min-h-screen flex-col">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#1e1e2e] px-6 py-4">
            <div>
              <p className="text-2xl font-semibold text-white">{p?.company_name || p?.domain}</p>
              <p className="text-sm text-ink-200">{p?.domain} · {p?.industry || "—"}</p>
            </div>
            <div className="text-right font-mono text-lg text-signal">
              {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
            </div>
            <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" asChild>
              <Link href={`/crm/prospects/${id}`}>Exit</Link>
            </Button>
          </header>

          <div className="grid flex-1 gap-6 p-6 lg:grid-cols-2">
            <section className={`space-y-4 p-6 ${crmSurfaceCard}`}>
              <h2 className="text-lg font-medium text-white">Loaded scan</h2>
              <div className="flex flex-col items-center justify-center gap-2 py-4">
                <HawkScoreRing
                  score={scan?.hawk_score ?? p?.hawk_score ?? 0}
                  size={120}
                  showEmptyState={!scan}
                />
                <span className="text-sm text-ink-200">Grade {(scan?.grade as string) || "—"}</span>
              </div>
              <ul className="space-y-2 text-sm text-ink-100">
                {topFindings.map((f, i) => (
                  <li key={i}>
                    {(f as { title?: string }).title || "Finding"}: {(f as { interpretation?: string }).interpretation || (f as { description?: string }).description || ""}
                  </li>
                ))}
              </ul>
            </section>

            <section className={`space-y-4 p-6 ${crmSurfaceCard}`}>
              <h2 className="text-lg font-medium text-white">Live deep scan</h2>
              <Button
                className="w-full bg-signal-400 py-6 text-lg"
                disabled={scanning}
                onClick={() => void runLiveScan()}
              >
                {scanning ? PHASES[phaseIdx] : "Run live scan"}
              </Button>
              {scanning && (
                <div className="h-2 w-full overflow-hidden rounded bg-[#0d0d14]">
                  <div
                    className="h-full bg-signal transition-all duration-1000"
                    style={{ width: `${((phaseIdx + 1) / PHASES.length) * 100}%` }}
                  />
                </div>
              )}
            </section>
          </div>

          <footer className="border-t border-[#1e1e2e] px-6 py-4">
            <p className="text-xs text-ink-0">Objections (← →). {pool[objIdx]?.q}</p>
            <p className="text-sm text-ink-100">{pool[objIdx]?.a}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" size="sm" asChild>
                <a href={`mailto:${p?.contact_email || ""}?subject=Your HAWK security report`}>Send report (email)</a>
              </Button>
              <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" size="sm" asChild>
                <Link href="/portal">Start subscription (portal)</Link>
              </Button>
            </div>
          </footer>
        </div>
      )}
    </div>
  );
}
