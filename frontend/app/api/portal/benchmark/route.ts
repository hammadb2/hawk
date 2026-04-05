import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** Peer fast scans can take several minutes on first benchmark build. */
export const maxDuration = 300;

export async function GET() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const res = await fetch(`${API_URL}/api/portal/benchmark`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });

  const text = await res.text();
  let j: Record<string, unknown> = {};
  try {
    if (text) j = JSON.parse(text) as Record<string, unknown>;
  } catch {
    /* ignore */
  }

  if (!res.ok) {
    return NextResponse.json({ error: (j.detail as string) || text }, { status: res.status });
  }

  return NextResponse.json(j);
}
