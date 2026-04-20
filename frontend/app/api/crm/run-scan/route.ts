import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/** Enqueue only — scan runs on Railway worker; no long Vercel wait (Rule 9). */
export const maxDuration = 30;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Start async CRM scan: returns job_id. Client polls GET /api/crm/scan-job/[jobId] then POST finalize.
 */
export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: { prospectId?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const prospectId = body.prospectId;
  if (!prospectId) {
    return NextResponse.json({ error: "prospectId required" }, { status: 400 });
  }

  const { data: prospect, error: pe } = await supabase
    .from("prospects")
    .select("id, domain, industry, stage, active_scan_job_id, scan_started_at")
    .eq("id", prospectId)
    .single();
  if (pe || !prospect) {
    return NextResponse.json({ error: "Prospect not found" }, { status: 404 });
  }

  // Block if another scan (manual or SLA auto) is already in flight and fresh.
  // Stale jobs (> 20 min, beyond the frontend poll timeout) are treated as
  // dead and silently replaced. The backend watchdog releases stuck SLA jobs
  // after SLA_SCAN_WATCHDOG_MIN (default 15 min), so this is consistent.
  if (prospect.active_scan_job_id) {
    const startedAt = prospect.scan_started_at ? Date.parse(prospect.scan_started_at) : 0;
    const ageMs = Date.now() - startedAt;
    const STALE_MS = 20 * 60 * 1000;
    if (startedAt && ageMs < STALE_MS) {
      return NextResponse.json(
        {
          error: "Scan already in progress",
          job_id: prospect.active_scan_job_id,
          started_at: prospect.scan_started_at,
        },
        { status: 409 },
      );
    }
  }

  const domain = String(prospect.domain).trim();
  const base = API_URL.replace(/\/$/, "");
  const industry = prospect.industry != null ? String(prospect.industry).trim() || null : null;

  let enq: Response;
  try {
    enq = await fetch(`${base}/api/scan/enqueue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, industry, scan_depth: "full" }),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: "Could not reach HAWK API", detail: `Check NEXT_PUBLIC_API_URL (${base}). ${msg}` },
      { status: 502 },
    );
  }

  if (!enq.ok) {
    const t = await enq.text();
    return NextResponse.json({ error: "Enqueue failed", detail: t.slice(0, 800) }, { status: 502 });
  }

  const j = (await enq.json()) as { job_id?: string };
  if (!j.job_id) {
    return NextResponse.json({ error: "No job_id from API" }, { status: 502 });
  }

  // Persist scanning state so the UI survives a page reload mid-scan. Also
  // advance stage=new -> stage=scanning so the pipeline board reflects the
  // in-flight scan. Never regress stage if a rep has already moved the
  // prospect past `new` (sent_email, replied, etc.); just refresh scan state.
  const now = new Date().toISOString();
  const scanUpdate: Record<string, unknown> = {
    active_scan_job_id: j.job_id,
    scan_started_at: now,
    scan_last_polled_at: now,
    scan_trigger: "manual",
  };
  if (prospect.stage === "new" || prospect.stage == null) {
    scanUpdate.stage = "scanning";
  }
  await supabase.from("prospects").update(scanUpdate).eq("id", prospectId);

  return NextResponse.json({ job_id: j.job_id, prospect_id: prospectId });
}
