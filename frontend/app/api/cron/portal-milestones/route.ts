import { NextResponse } from "next/server";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

function cronAuthorized(request: Request): boolean {
  const secret =
    process.env.CRON_SECRET?.trim() ||
    process.env.HAWK_CRM_CRON_SECRET?.trim() ||
    process.env.HAWK_CRON_SECRET?.trim();
  if (!secret) return false;
  const auth = request.headers.get("authorization");
  if (auth === `Bearer ${secret}`) return true;
  if (request.headers.get("x-cron-secret") === secret) return true;
  return false;
}

/** Awards portal journey milestones for all linked clients (daily). */
export async function GET(request: Request) {
  if (!cronAuthorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const secret =
    process.env.CRON_SECRET?.trim() ||
    process.env.HAWK_CRM_CRON_SECRET?.trim() ||
    process.env.HAWK_CRON_SECRET?.trim();
  if (!secret) {
    return NextResponse.json({ error: "CRON_SECRET not configured" }, { status: 503 });
  }

  const res = await fetch(`${API_URL}/api/crm/cron/portal-milestones`, {
    method: "POST",
    headers: { "X-Cron-Secret": secret },
  });

  const text = await res.text();
  let j: Record<string, unknown> = {};
  try {
    if (text) j = JSON.parse(text) as Record<string, unknown>;
  } catch {
    /* ignore */
  }

  if (!res.ok) {
    return NextResponse.json(
      { error: typeof j.detail === "string" ? j.detail : text.slice(0, 400) },
      { status: res.status },
    );
  }

  return NextResponse.json(j);
}
