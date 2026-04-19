import { NextRequest, NextResponse } from "next/server";

function normalizeApiBase(raw: string): string {
  const t = raw.trim().replace(/\/$/, "");
  if (t.startsWith("http://") || t.startsWith("https://")) return t;
  return `https://${t}`;
}

/**
 * Railway / FastAPI origin. Must NOT be the same host as this Next site (avoids self-fetch → 404 loop).
 */
function crmApiBase(req: NextRequest): string | null {
  const requestHost = (req.headers.get("host") || "").toLowerCase();

  for (const envName of ["CRM_API_BASE_URL", "NEXT_PUBLIC_API_URL"] as const) {
    const raw = process.env[envName]?.trim();
    if (!raw) continue;
    let base: string;
    try {
      base = normalizeApiBase(raw);
      const u = new URL(base);
      if (requestHost && u.host === requestHost) {
        // e.g. NEXT_PUBLIC_API_URL=https://securedbyhawk.com — server would POST to itself → 404
        continue;
      }
      return base;
    } catch {
      continue;
    }
  }

  if (process.env.VERCEL !== "1" && process.env.NODE_ENV !== "production") {
    return "http://localhost:8000";
  }
  return null;
}

/**
 * Proxy Cal.com → Railway FastAPI `POST /api/crm/webhooks/cal`.
 * Raw body bytes + signature headers preserved for HMAC verification.
 */
export async function POST(req: NextRequest) {
  const base = crmApiBase(req);
  if (!base) {
    return NextResponse.json(
      {
        error:
          "Misconfigured API base: set Vercel env CRM_API_BASE_URL to your Railway FastAPI origin (no trailing slash), e.g. https://intelligent-rejoicing-production.up.railway.app. Do not point it at securedbyhawk.com.",
      },
      { status: 503 },
    );
  }

  const raw = await req.arrayBuffer();
  const signature =
    req.headers.get("x-cal-signature-256") ?? req.headers.get("X-Cal-Signature-256") ?? "";
  const contentType = req.headers.get("Content-Type") || "application/json";
  const webhookVersion = req.headers.get("x-cal-webhook-version") ?? req.headers.get("X-Cal-Webhook-Version");

  const headers: Record<string, string> = {
    "Content-Type": contentType,
    "X-Cal-Signature-256": signature,
  };
  if (webhookVersion) {
    headers["X-Cal-Webhook-Version"] = webhookVersion;
  }

  const upstreamUrl = `${base}/api/crm/webhooks/cal`;
  let backendRes: Response;
  try {
    backendRes = await fetch(upstreamUrl, {
      method: "POST",
      headers,
      body: raw.byteLength ? new Uint8Array(raw) : undefined,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: "Upstream fetch failed", detail: msg, upstreamUrl }, { status: 502 });
  }

  const payload = await backendRes.json().catch(() => ({}));
  const res = NextResponse.json(payload, { status: backendRes.status });
  if (backendRes.status === 404) {
    res.headers.set("X-Proxy-Upstream", upstreamUrl);
  }
  return res;
}

/** Confirms this Next route exists; Cal.com ping uses POST. */
export async function GET(req: NextRequest) {
  const base = crmApiBase(req);
  return NextResponse.json({
    ok: true,
    route: "/api/crm/webhooks/cal",
    upstream: base ? `${base}/api/crm/webhooks/cal` : null,
    configured: Boolean(base),
    hint: base
      ? "POST Cal payloads here; they are proxied to upstream."
      : "Set CRM_API_BASE_URL on Vercel to your Railway API origin.",
  });
}
