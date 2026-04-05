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
  ],
  dental: [
    { q: "We use a managed IT vendor.", a: "Great. This shows what shows up from the outside on your domain, vendor aside." },
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
  const ind = p?.industry?.toLowerCase().includes("dental") ? "dental" : "default";
  const pool = OBJECTIONS[ind] ?? OBJECTIONS.default;

  if (!id) return <p className="p-6 text-zinc-500">Invalid</p>;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <Dialog open={briefOpen} onOpenChange={setBriefOpen}>
        <DialogContent className="border-zinc-800 bg-zinc-900 text-zinc-100">
          <DialogHeader>
            <DialogTitle>Pre-call brief</DialogTitle>
          </DialogHeader>
          <p className="text-sm leading-relaxed">
            Calling {p?.contact_name || "the prospect"} at {p?.company_name || p?.domain}
            <br />
            Score: {scan?.hawk_score ?? p?.hawk_score ?? "—"}/100 — Grade {(scan?.grade as string) || "—"}
            <br />
            Industry: {p?.industry || "—"}
          </p>
          <DialogFooter>
            <Button className="bg-emerald-600" onClick={() => { setBriefOpen(false); setEntered(true); setStarted(Date.now()); }}>
              Enter call mode
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {entered && (
        <div className="flex min-h-screen flex-col">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 px-6 py-4">
            <div>
              <p className="text-2xl font-semibold">{p?.company_name || p?.domain}</p>
              <p className="text-sm text-zinc-400">{p?.domain} · {p?.industry || "—"}</p>
            </div>
            <div className="text-right font-mono text-lg text-emerald-400">
              {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
            </div>
            <Button variant="outline" className="border-zinc-700" asChild>
              <Link href={`/crm/prospects/${id}`}>Exit</Link>
            </Button>
          </header>

          <div className="grid flex-1 gap-6 p-6 lg:grid-cols-2">
            <section className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
              <h2 className="text-lg font-medium text-zinc-200">Loaded scan</h2>
              <div className="flex flex-col items-center justify-center gap-2 py-4">
                <HawkScoreRing score={scan?.hawk_score ?? p?.hawk_score ?? 0} size={120} />
                <span className="text-sm text-zinc-400">Grade {(scan?.grade as string) || "—"}</span>
              </div>
              <ul className="space-y-2 text-sm text-zinc-300">
                {topFindings.map((f, i) => (
                  <li key={i}>
                    {(f as { title?: string }).title || "Finding"}: {(f as { interpretation?: string }).interpretation || (f as { description?: string }).description || ""}
                  </li>
                ))}
              </ul>
            </section>

            <section className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
              <h2 className="text-lg font-medium text-zinc-200">Live deep scan</h2>
              <Button
                className="w-full bg-emerald-600 py-6 text-lg"
                disabled={scanning}
                onClick={() => void runLiveScan()}
              >
                {scanning ? PHASES[phaseIdx] : "Run live scan"}
              </Button>
              {scanning && (
                <div className="h-2 w-full overflow-hidden rounded bg-zinc-800">
                  <div
                    className="h-full bg-emerald-500 transition-all duration-1000"
                    style={{ width: `${((phaseIdx + 1) / PHASES.length) * 100}%` }}
                  />
                </div>
              )}
            </section>
          </div>

          <footer className="border-t border-zinc-800 px-6 py-4">
            <p className="text-xs text-zinc-500">Objections (← →). {pool[objIdx]?.q}</p>
            <p className="text-sm text-zinc-300">{pool[objIdx]?.a}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="outline" className="border-zinc-700" size="sm" asChild>
                <a href={`mailto:${p?.contact_email || ""}?subject=Your HAWK security report`}>Send report (email)</a>
              </Button>
              <Button variant="outline" className="border-zinc-700" size="sm" asChild>
                <Link href="/portal">Start subscription (portal)</Link>
              </Button>
            </div>
          </footer>
        </div>
      )}
    </div>
  );
}
