/**
 * Server-side URL for proxying /api/* to FastAPI (Railway).
 * Set HAWK_API_URL in Vercel (origin only, e.g. https://xxx.up.railway.app — not .../api).
 */
export function backendApiBase(): string {
  let base = (process.env.HAWK_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  if (base.endsWith("/api")) {
    base = base.slice(0, -4);
  }
  return base;
}
