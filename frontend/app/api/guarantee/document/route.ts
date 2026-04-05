import { NextResponse } from "next/server";
import { backendApiBase } from "@/lib/backend-proxy";

export async function GET(req: Request) {
  const auth = req.headers.get("authorization");
  try {
    const r = await fetch(`${backendApiBase()}/api/guarantee/document`, {
      headers: auth ? { Authorization: auth } : {},
    });
    const data = await r.json().catch(() => ({}));
    return NextResponse.json(data, { status: r.status });
  } catch (e) {
    console.error("guarantee document proxy:", e);
    return NextResponse.json({ detail: "Upstream unavailable" }, { status: 502 });
  }
}
