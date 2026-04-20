import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const maxDuration = 60;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ScanResult = {
  domain?: string;
  status?: string;
  score?: number;
  grade?: string;
  findings?: unknown[];
  scan_version?: string;
  industry?: string | null;
  raw_layers?: Record<string, unknown>;
  interpreted_findings?: unknown[];
  breach_cost_estimate?: Record<string, unknown>;
  attack_paths?: unknown[];
};

function asFindingRecord(f: unknown): Record<string, unknown> | null {
  if (!f || typeof f !== "object") return null;
  return f as Record<string, unknown>;
}

/** Persist interpreted / attack-path rows even if the job payload nests them under raw_layers or only merged into findings[]. */
function resolveInterpretedFindings(r: ScanResult, findingsList: unknown[]): unknown[] {
  const direct = r.interpreted_findings;
  if (Array.isArray(direct) && direct.length > 0) return direct;

  const raw = r.raw_layers;
  const nested =
    raw && typeof raw === "object" && Array.isArray((raw as Record<string, unknown>).interpreted_findings)
      ? ((raw as Record<string, unknown>).interpreted_findings as unknown[])
      : [];
  if (nested.length > 0) return nested;

  const rebuilt: unknown[] = [];
  for (const f of findingsList) {
    const o = asFindingRecord(f);
    if (!o) continue;
    const id = o.id;
    const plain =
      (typeof o.interpretation === "string" && o.interpretation) ||
      (typeof o.plain_english === "string" && o.plain_english) ||
      (typeof o.description === "string" && o.description) ||
      "";
    const fix =
      (typeof o.fix_guide === "string" && o.fix_guide) ||
      (typeof o.remediation === "string" && o.remediation) ||
      "";
    if (!plain && !fix && id == null) continue;
    rebuilt.push({
      id,
      plain_english: plain,
      fix_guide: fix || undefined,
    });
  }
  return rebuilt;
}

function resolveAttackPaths(r: ScanResult): unknown[] {
  const direct = r.attack_paths;
  if (Array.isArray(direct) && direct.length > 0) return direct;
  const raw = r.raw_layers;
  if (raw && typeof raw === "object") {
    const ap = (raw as Record<string, unknown>).attack_paths;
    if (Array.isArray(ap) && ap.length > 0) return ap;
  }
  return Array.isArray(direct) ? direct : [];
}

/** Persist completed async scan to Supabase (idempotent by external_job_id). */
export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: { jobId?: string; prospectId?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const jobId = body.jobId;
  const prospectId = body.prospectId;
  if (!jobId || !prospectId) {
    return NextResponse.json({ error: "jobId and prospectId required" }, { status: 400 });
  }

  const { data: existing } = await supabase
    .from("crm_prospect_scans")
    .select("id")
    .eq("external_job_id", jobId)
    .maybeSingle();
  if (existing?.id) {
    return NextResponse.json({ ok: true, duplicate: true, scan_id: existing.id });
  }

  const base = API_URL.replace(/\/$/, "");
  let res: Response;
  try {
    res = await fetch(`${base}/api/scan/job/${encodeURIComponent(jobId)}`, { method: "GET" });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: "Could not fetch job", detail: msg }, { status: 502 });
  }

  const rawText = await res.text();
  if (!res.ok) {
    return NextResponse.json({ error: "Job not available", detail: rawText.slice(0, 800) }, { status: res.status });
  }

  let job: { status?: string; result?: ScanResult; error?: string };
  try {
    job = JSON.parse(rawText) as typeof job;
  } catch {
    return NextResponse.json({ error: "Invalid job JSON" }, { status: 502 });
  }

  if (job.status === "failed") {
    return NextResponse.json({ error: job.error || "Scan job failed" }, { status: 502 });
  }
  if (job.status !== "complete" || !job.result) {
    return NextResponse.json({ error: "Job not complete yet", status: job.status }, { status: 409 });
  }

  const r = job.result;
  const findingsList = Array.isArray(r.findings) ? r.findings : [];
  const interpretedPersisted = resolveInterpretedFindings(r, findingsList);
  const attackPathsPersisted = resolveAttackPaths(r);
  const score = typeof r.score === "number" ? r.score : 0;

  const { data: prospect, error: pe } = await supabase
    .from("prospects")
    .select("id, hawk_score, industry, stage")
    .eq("id", prospectId)
    .single();
  if (pe || !prospect) {
    return NextResponse.json({ error: "Prospect not found" }, { status: 404 });
  }

  const industryStored = r.industry ?? prospect.industry ?? null;
  const findingsPayload = {
    source: "hawk_scanner_v2_async",
    findings: findingsList,
  };

  const { error: insErr, data: inserted } = await supabase
    .from("crm_prospect_scans")
    .insert({
      prospect_id: prospectId,
      hawk_score: score,
      grade: r.grade ?? null,
      findings: findingsPayload as unknown as Record<string, unknown>,
      status: "complete",
      triggered_by: user.id,
      scan_version: r.scan_version ?? "2.0",
      industry: industryStored,
      raw_layers: (r.raw_layers ?? {}) as Record<string, unknown>,
      interpreted_findings: interpretedPersisted,
      breach_cost_estimate: (r.breach_cost_estimate ?? {}) as Record<string, unknown>,
      attack_paths: attackPathsPersisted,
      external_job_id: jobId,
    })
    .select("id")
    .single();

  if (insErr) {
    return NextResponse.json({ error: insErr.message }, { status: 500 });
  }

  const scoreBefore = typeof prospect.hawk_score === "number" ? prospect.hawk_score : null;

  const nowIso = new Date().toISOString();
  // Only advance stage/pipeline_status from "new" or "scanning" → "scanned".
  // If the prospect has already moved further down the funnel (sent_email,
  // replied, call_booked, closed_won, lost) we leave them where they are and
  // only refresh the scan-related fields.
  const shouldAdvanceStage =
    prospect.stage === "new" || prospect.stage === "scanning" || prospect.stage == null;
  const prospectUpdate: Record<string, unknown> = {
    hawk_score: score,
    last_activity_at: nowIso,
    scanned_at: nowIso,
    active_scan_job_id: null,
    scan_started_at: null,
    scan_last_polled_at: null,
    scan_trigger: null,
  };
  if (shouldAdvanceStage) {
    prospectUpdate.stage = "scanned";
    prospectUpdate.pipeline_status = "scanned";
  }
  await supabase.from("prospects").update(prospectUpdate).eq("id", prospectId);

  await supabase.from("activities").insert({
    prospect_id: prospectId,
    type: "scan_run",
    created_by: user.id,
    notes: null,
    metadata: { score_before: scoreBefore, score_after: score, grade: r.grade },
  });

  return NextResponse.json({
    ok: true,
    scan_id: inserted?.id,
    score,
    grade: r.grade,
    findings_count: findingsList.length,
  });
}
