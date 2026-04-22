import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Proxy the vertical aware US compliance PDF from the API (portal session cookie to Bearer). */
export async function GET() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const base = API_URL.replace(/\/$/, "");
  const res = await fetch(`${base}/api/portal/compliance-report.pdf`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });

  if (!res.ok) {
    const t = await res.text();
    return NextResponse.json({ error: t.slice(0, 400) }, { status: res.status });
  }

  const buf = await res.arrayBuffer();
  return new NextResponse(buf, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'attachment; filename="hawk-compliance-overview.pdf"',
    },
  });
}
