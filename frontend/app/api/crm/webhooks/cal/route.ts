import { NextResponse } from "next/server";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/**
 * Proxy Cal.com → Railway FastAPI `POST /api/crm/webhooks/cal`.
 * Cal.com "Ping test" and production webhooks often target the public site
 * (e.g. securedbyhawk.com); Next had no route → 404 before this file existed.
 * Forwards raw body bytes unchanged so HMAC (X-Cal-Signature-256) still verifies on the API.
 */
export async function POST(request: Request) {
  const raw = await request.arrayBuffer();
  const sig = request.headers.get("x-cal-signature-256");
  const ct = request.headers.get("content-type") || "application/json";

  const headers: HeadersInit = { "Content-Type": ct };
  if (sig) headers["X-Cal-Signature-256"] = sig;

  const res = await fetch(`${API_URL}/api/crm/webhooks/cal`, {
    method: "POST",
    headers,
    body: raw.byteLength ? new Uint8Array(raw) : undefined,
  });

  const text = await res.text();
  const outCt = res.headers.get("content-type") || "application/json";

  if (!res.ok) {
    return new NextResponse(text || JSON.stringify({ detail: "upstream error" }), {
      status: res.status,
      headers: { "Content-Type": outCt },
    });
  }

  try {
    const j = text ? JSON.parse(text) : {};
    return NextResponse.json(j, { status: res.status });
  } catch {
    return new NextResponse(text, { status: res.status, headers: { "Content-Type": outCt } });
  }
}

/** Optional connectivity check from browser or docs (Cal.com uses POST for ping). */
export async function GET() {
  return NextResponse.json({
    ok: true,
    route: "/api/crm/webhooks/cal",
    note: "Cal.com ping and events use POST; this GET only confirms the Next.js route exists.",
    upstream: `${API_URL}/api/crm/webhooks/cal`,
  });
}
