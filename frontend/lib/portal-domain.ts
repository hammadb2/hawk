/** Align with backend portal_bootstrap public-mail handling (generic inbox → need real apex). */

const PUBLIC_MAIL_HOSTS = new Set([
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "yahoo.co.uk",
  "hotmail.com",
  "outlook.com",
  "live.com",
  "msn.com",
  "icloud.com",
  "me.com",
  "aol.com",
  "protonmail.com",
  "proton.me",
  "gmx.com",
  "zoho.com",
  "yandex.com",
  "fastmail.com",
  "mail.com",
]);

const SYNTHETIC_MAIL_TAILS = [
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "hotmail.com",
  "outlook.com",
  "live.com",
  "icloud.com",
  "me.com",
  "msn.com",
  "aol.com",
];

export function isPublicMailHost(host: string | undefined | null): boolean {
  if (!host) return false;
  return PUBLIC_MAIL_HOSTS.has(host.trim().toLowerCase());
}

/** Bootstrap stores localpart.host (e.g. jamie.gmail.com) when the inbox is on a shared provider. */
export function looksLikeSyntheticPortalDomain(domain: string | null | undefined): boolean {
  const d = (domain || "").trim().toLowerCase();
  if (!d || !d.includes(".")) return false;
  const parts = d.split(".");
  if (parts.length < 3) return false;
  const tail = parts.slice(-2).join(".");
  return SYNTHETIC_MAIL_TAILS.includes(tail);
}

/** Entire clients.domain is a shared public apex (legacy / wrong) — need a real company apex. */
export function isPublicMailApexDomain(domain: string | null | undefined): boolean {
  const d = (domain || "").trim().toLowerCase();
  return Boolean(d && PUBLIC_MAIL_HOSTS.has(d));
}

/**
 * True when we still need the customer to give a real company apex for scanning (generic inbox or synthetic key).
 * False once clients.domain is a non-public apex (e.g. acme.com), even if sign-in email is still Gmail.
 */
export function needsCompanyDomainForMonitoring(userEmail: string | undefined | null, cppDomain: string | null | undefined): boolean {
  const em = (userEmail || "").trim().toLowerCase();
  const host = em.includes("@") ? em.split("@")[1] : "";
  const d = (cppDomain || "").trim().toLowerCase();

  if (isPublicMailApexDomain(d)) return true;
  if (looksLikeSyntheticPortalDomain(cppDomain)) return true;
  if (isPublicMailHost(host) && !d) return true;
  if (isPublicMailHost(host) && d && !looksLikeSyntheticPortalDomain(cppDomain) && !isPublicMailApexDomain(d)) return false;
  return false;
}
