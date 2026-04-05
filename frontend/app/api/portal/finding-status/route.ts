import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const maxDuration = 60;

export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: { prospectId?: string; scanId?: string; findingId?: string; status?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  if (!body.prospectId || !body.scanId || !body.findingId || !body.status) {
    return NextResponse.json({ error: "prospectId, scanId, findingId, status required" }, { status: 400 });
  }

  const res = await fetch(`${API_URL}/api/portal/finding-status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      prospect_id: body.prospectId,
      scan_id: body.scanId,
      finding_id: body.findingId,
      status: body.status,
    }),
  });

  const text = await res.text();
  let j: Record<string, unknown> = {};
  try {
    if (text) j = JSON.parse(text) as Record<string, unknown>;
  } catch {
    /* ignore */
  }

  if (!res.ok) {
    const detail = j.detail;
    const detailStr =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x)))
              .join("; ")
          : undefined;
    return NextResponse.json({ error: detailStr || text.slice(0, 400) }, { status: res.status });
  }

  return NextResponse.json(j);
}
