import { NextResponse } from "next/server";
import { backendApiBase } from "@/lib/backend-proxy";

export async function POST(req: Request) {
  const body = await req.text();
  try {
    const r = await fetch(`${backendApiBase()}/api/guarantee/request-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const data = await r.json().catch(() => ({}));
    return NextResponse.json(data, { status: r.status });
  } catch (e) {
    console.error("guarantee request-code proxy:", e);
    return NextResponse.json({ detail: "Upstream unavailable" }, { status: 502 });
  }
}
