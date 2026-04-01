import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const maxDuration = 30;

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type RouteCtx = { params: Promise<{ jobId: string }> };

/** Poll scanner job status (proxies Railway API). */
export async function GET(_request: Request, context: RouteCtx) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { jobId } = await context.params;
  if (!jobId) {
    return NextResponse.json({ error: "jobId required" }, { status: 400 });
  }

  const base = API_URL.replace(/\/$/, "");
  let res: Response;
  try {
    res = await fetch(`${base}/api/scan/job/${encodeURIComponent(jobId)}`, { method: "GET" });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: "Upstream unreachable", detail: msg }, { status: 502 });
  }

  const text = await res.text();
  if (!res.ok) {
    return NextResponse.json({ error: "Job fetch failed", detail: text.slice(0, 800) }, { status: res.status });
  }

  try {
    return NextResponse.json(JSON.parse(text) as object);
  } catch {
    return NextResponse.json({ error: "Invalid JSON from scanner" }, { status: 502 });
  }
}
