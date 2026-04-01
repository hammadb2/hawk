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
    .select("id, domain, industry")
    .eq("id", prospectId)
    .single();
  if (pe || !prospect) {
    return NextResponse.json({ error: "Prospect not found" }, { status: 404 });
  }

  const domain = String(prospect.domain).trim();
  const base = API_URL.replace(/\/$/, "");
  const industry = prospect.industry != null ? String(prospect.industry).trim() || null : null;

  let enq: Response;
  try {
    enq = await fetch(`${base}/api/scan/enqueue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, industry }),
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

  return NextResponse.json({ job_id: j.job_id, prospect_id: prospectId });
}
