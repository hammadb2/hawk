import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** Server proxy: set monitored apex domain (`POST /api/portal/primary-domain` on API). */
export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const res = await fetch(`${API_URL}/api/portal/primary-domain`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify(body),
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
