import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * Vercel serverless limit for this route. Full scanner pipeline often runs 2–5+ minutes.
 * Hobby caps lower; Pro/Enterprise supports up to 300s (see Vercel dashboard → Functions).
 */
export const maxDuration = 300;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Stay slightly under maxDuration so the fetch aborts before Vercel kills the function */
const SCAN_FETCH_MS = 295_000;

/** Parse FastAPI-style JSON error body: { "detail": "..." } or validation array */
function parseUpstreamError(text: string): string {
  try {
    const j = JSON.parse(text) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) {
      return j.detail
        .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: string }).msg) : String(x)))
        .join("; ");
    }
  } catch {
    /* ignore */
  }
  return text.slice(0, 800);
}

/**
 * CRM prospect scan: Supabase auth → POST {domain} to Railway /api/scan/public
 * (see backend/services/scanner.py → HAWK_SCANNER_RELAY_URL, default Ghost http://178.104.27.211:8002/scan).
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

  const { data: prospect, error: pe } = await supabase.from("prospects").select("id, domain").eq("id", prospectId).single();
  if (pe || !prospect) {
    return NextResponse.json({ error: "Prospect not found" }, { status: 404 });
  }

  const domain = String(prospect.domain).trim();
  const base = API_URL.replace(/\/$/, "");

  let scanRes: Response;
  try {
    scanRes = await fetch(`${base}/api/scan/public`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain }),
      signal: AbortSignal.timeout(SCAN_FETCH_MS),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      {
        error: "Could not reach HAWK API",
        detail: `Check NEXT_PUBLIC_API_URL (${base}) points to your Railway service. ${msg}`,
      },
      { status: 502 },
    );
  }

  if (!scanRes.ok) {
    const errText = await scanRes.text();
    const detail = parseUpstreamError(errText);
    return NextResponse.json({ error: "Scanner failed", detail }, { status: 502 });
  }

  const scanJson = (await scanRes.json()) as {
    domain?: string;
    status?: string;
    score?: number;
    grade?: string;
    findings_count?: number;
  };

  const findings = {
    source: "hawk_public_scan",
    grade: scanJson.grade ?? null,
    findings_count: scanJson.findings_count ?? null,
  };

  const score = typeof scanJson.score === "number" ? scanJson.score : 0;

  const { error: insErr } = await supabase.from("crm_prospect_scans").insert({
    prospect_id: prospectId,
    hawk_score: score,
    grade: scanJson.grade ?? null,
    findings: findings as unknown as Record<string, unknown>,
    status: "complete",
    triggered_by: user.id,
  });
  if (insErr) {
    return NextResponse.json({ error: insErr.message }, { status: 500 });
  }

  await supabase
    .from("prospects")
    .update({ hawk_score: score, last_activity_at: new Date().toISOString() })
    .eq("id", prospectId);

  await supabase.from("activities").insert({
    prospect_id: prospectId,
    type: "scan_run",
    created_by: user.id,
    notes: null,
    metadata: { score_before: null, score_after: score, grade: scanJson.grade },
  });

  return NextResponse.json({ ok: true, score, grade: scanJson.grade, findings_count: scanJson.findings_count });
}
