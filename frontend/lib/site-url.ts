/**
 * Canonical public site origin (no trailing slash).
 * Set NEXT_PUBLIC_SITE_URL in Vercel (e.g. https://securedbyhawk.com). Magic links must use this exact origin
 * so Supabase does not fall back to the project Site URL (often "/" only).
 */
const FALLBACK_PRODUCTION_ORIGIN = "https://securedbyhawk.com";

/** Production-safe origin: env wins; otherwise securedbyhawk.com (not window.location — avoids relative / wrong host). */
export function getPublicSiteOrigin(): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "");
  if (env) return env;
  if (typeof window !== "undefined") {
    const { hostname } = window.location;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return window.location.origin;
    }
  }
  return FALLBACK_PRODUCTION_ORIGIN;
}

export function getPublicSiteUrlFromRequest(requestUrl: string): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "");
  if (env) return env;
  return new URL(requestUrl).origin;
}

/**
 * Full URL for CRM magic link return — must be absolute and listed in Supabase Auth → Redirect URLs.
 * Example: https://securedbyhawk.com/crm/auth/callback?next=%2Fcrm%2Fdashboard
 */
export function getCrmMagicLinkCallbackUrl(nextPath: string): string {
  const origin = getPublicSiteOrigin();
  const path = nextPath.startsWith("/") ? nextPath : `/${nextPath}`;
  const u = new URL(`${origin}/crm/auth/callback`);
  u.searchParams.set("next", path);
  return u.toString();
}

/**
 * Portal magic link — absolute URL for emailRedirectTo.
 * @param nextPath path after callback (e.g. /portal/billing?plan=shield), default /portal
 */
export function getPortalMagicLinkCallbackUrl(nextPath = "/portal"): string {
  const origin = getPublicSiteOrigin();
  const path = nextPath.startsWith("/") ? nextPath : `/${nextPath}`;
  const u = new URL(`${origin}/portal/auth/callback`);
  u.searchParams.set("next", path);
  return u.toString();
}

/**
 * After Supabase magic link, `next` must stay under /portal. Treat `/` and bare marketing paths as /portal
 * so misconfigured Site URL or empty next does not send users to the marketing home page.
 */
export function safePortalNextPath(raw: string | null, fallback = "/portal"): string {
  if (!raw) return fallback;
  try {
    const p = decodeURIComponent(raw).trim();
    if (!p.startsWith("/") || p.startsWith("//") || p.includes("://")) return fallback;
    if (p === "/" || p === "/index" || p === "/home") return fallback;
    if (!p.startsWith("/portal")) return fallback;
    return p;
  } catch {
    return fallback;
  }
}
