import { NextRequest, NextResponse } from "next/server";

/** Vercel: set to FastAPI origin (no trailing slash), e.g. https://intelligent-rejoicing-production.up.railway.app */
function crmApiBase(): string {
  const raw =
    process.env.CRM_API_BASE_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "http://localhost:8000";
  return raw.replace(/\/$/, "");
}

/**
 * Proxy Cal.com → Railway FastAPI `POST /api/crm/webhooks/cal`.
 * securedbyhawk.com is Next on Vercel; Cal must hit this route so the body + signature reach FastAPI unchanged.
 */
export async function POST(req: NextRequest) {
  const body = await req.text();
  const signature = req.headers.get("X-Cal-Signature-256") ?? "";
  const contentType = req.headers.get("Content-Type") || "application/json";

  const backendRes = await fetch(`${crmApiBase()}/api/crm/webhooks/cal`, {
    method: "POST",
    headers: {
      "Content-Type": contentType,
      "X-Cal-Signature-256": signature,
    },
    body,
  });

  return NextResponse.json(await backendRes.json().catch(() => ({})), { status: backendRes.status });
}

/** Confirms this Next route exists; Cal.com ping uses POST. */
export async function GET() {
  return NextResponse.json({
    ok: true,
    route: "/api/crm/webhooks/cal",
    upstream: `${crmApiBase()}/api/crm/webhooks/cal`,
    env: process.env.CRM_API_BASE_URL ? "CRM_API_BASE_URL" : process.env.NEXT_PUBLIC_API_URL ? "NEXT_PUBLIC_API_URL" : "default localhost",
  });
}
