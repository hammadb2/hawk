import { NextResponse } from "next/server";
import { backendApiBase } from "@/lib/backend-proxy";

/** Proxies to FastAPI POST /api/billing/checkout-public-test (Stripe test mode). */
export async function POST(req: Request) {
  const body = await req.text();
  try {
    const r = await fetch(`${backendApiBase()}/api/billing/checkout-public-test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const data = await r.json().catch(() => ({}));
    return NextResponse.json(data, { status: r.status });
  } catch (e) {
    console.error("checkout-public-test proxy:", e);
    return NextResponse.json({ detail: "Upstream unavailable" }, { status: 502 });
  }
}
