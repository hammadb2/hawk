import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export async function GET() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const res = await fetch(`${API_URL}/api/portal/journey/badge.png`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });

  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const j = JSON.parse(text) as { detail?: string };
      if (j.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    return NextResponse.json({ error: detail || `Upstream ${res.status}` }, { status: res.status });
  }

  const png = await res.arrayBuffer();
  return new Response(png, {
    status: 200,
    headers: {
      "Content-Type": "image/png",
      "Content-Disposition": 'attachment; filename="hawk-certified-badge.png"',
      "Cache-Control": "private, max-age=0",
    },
  });
}
