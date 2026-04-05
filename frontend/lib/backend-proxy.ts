/**
 * Server-side URL for proxying /api/* to FastAPI (Railway).
 * Set HAWK_API_URL in Vercel (same value as NEXT_PUBLIC_API_URL is fine).
 */
export function backendApiBase(): string {
  return (process.env.HAWK_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}
