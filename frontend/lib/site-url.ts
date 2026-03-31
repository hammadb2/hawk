/**
 * Canonical public site origin (no trailing slash).
 * Set NEXT_PUBLIC_SITE_URL on Vercel (e.g. https://securedbyhawk.com) for magic links, redirects, and emails.
 */
const FALLBACK_PRODUCTION_SITE = "https://securedbyhawk.com";

export function getPublicSiteUrlFromRequest(requestUrl: string): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "");
  if (env) return env;
  return new URL(requestUrl).origin;
}

/**
 * Client-only: use env when set (matches production domain during local dev if you set .env.local),
 * otherwise current window origin.
 */
export function getEmailRedirectOrigin(): string {
  if (typeof window !== "undefined") {
    return process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "") || window.location.origin;
  }
  return process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "") || FALLBACK_PRODUCTION_SITE;
}
