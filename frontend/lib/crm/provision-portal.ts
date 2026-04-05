export type ProvisionPortalResult =
  | { ok: true; invited_email?: string; idempotent?: boolean }
  | { ok: false; status: number; detail: string };

/**
 * After inserting a `clients` row on Close Won, provisions Supabase auth (invite),
 * profiles.role=client, client_portal_profiles, and sends portal magic link (redirect /portal).
 * Calls the Next.js API route (cookie session); the server forwards the bearer token to the API — not exposed cross-origin in the browser.
 */
export async function provisionClientPortalAfterCloseWon(clientId: string): Promise<ProvisionPortalResult> {
  const r = await fetch(`/api/crm/clients/${encodeURIComponent(clientId)}/provision-portal`, {
    method: "POST",
  });
  const text = await r.text();
  if (!r.ok) {
    let detail = text.slice(0, 400);
    try {
      const j = JSON.parse(text) as { detail?: unknown };
      if (typeof j.detail === "string") {
        detail = j.detail;
      } else if (Array.isArray(j.detail)) {
        detail = j.detail
          .map((x) =>
            typeof x === "object" && x !== null && "msg" in x ? String((x as { msg: string }).msg) : String(x)
          )
          .join("; ");
      }
    } catch {
      /* use raw */
    }
    return { ok: false, status: r.status, detail };
  }
  try {
    const j = JSON.parse(text) as { invited_email?: string; idempotent?: boolean };
    return { ok: true, invited_email: j.invited_email, idempotent: j.idempotent };
  } catch {
    return { ok: true };
  }
}
