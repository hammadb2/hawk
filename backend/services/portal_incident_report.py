"""One-click incident-report workflow (priority list #34).

When a client hits the "Report a security incident" button in the portal,
we:

1. Insert a row into ``client_incident_reports`` with an SLA deadline
   (``reported_at + HAWK_INCIDENT_SLA_MINUTES`` — default 60 minutes).
2. Fire an OpenPhone SMS to the CEO via :func:`services.crm_openphone.send_ceo_sms`.
   Gracefully degrades to ``skipped`` when ``OPENPHONE_API_KEY`` isn't
   configured — the incident is still logged.
3. Send a Resend confirmation email to the signed-in client so they have
   the case id and the SLA clock in writing.
4. Insert a mirror row in ``crm_support_tickets`` so internal reps pick
   it up in the CRM queue. Skipped (logged) when no CEO profile exists
   to be the ticket's ``requester_id``.

Each fan-out step is independent: if any fails the others still run and
the incident id + sla_deadline are returned so the UI can confirm.
"""

from __future__ import annotations

import html as html_mod
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from config import SUPABASE_URL
from services.crm_openphone import send_ceo_sms
from services.crm_portal_email import send_resend
from services.portal_bootstrap import _headers, get_client_id_for_portal_user

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
DEFAULT_SLA_MINUTES = int(os.environ.get("HAWK_INCIDENT_SLA_MINUTES", "60"))
CEO_EMAIL_FALLBACK = os.environ.get("HAWK_CEO_EMAIL", "").strip()


def _esc(s: str) -> str:
    return html_mod.escape(s or "", quote=True)


def _short_case_id(incident_id: str) -> str:
    """Short human-readable case id (first 8 chars of the uuid)."""
    return f"HAWK-{str(incident_id).split('-')[0].upper()}"


def _ceo_profile_id() -> str | None:
    """Look up a CEO profile to own the mirrored support ticket.

    Fall back to the head-of-support ('hos') if no CEO profile exists.
    Returns ``None`` when neither is found; the caller skips the ticket
    insert in that case rather than crashing the whole flow.
    """
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"role": "in.(ceo,hos)", "select": "id,role", "limit": "10"},
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.warning("incident_report: ceo profile lookup failed: %s %s", r.status_code, r.text[:300])
        return None
    rows = r.json()
    if not rows:
        return None
    # Prefer CEO, fall back to HoS.
    ceo = next((row for row in rows if row.get("role") == "ceo"), None)
    target = ceo or rows[0]
    pid = target.get("id")
    return str(pid) if pid else None


def _load_client_context(client_id: str) -> dict[str, Any]:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={"id": f"eq.{client_id}", "select": "id,company_name,domain", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise HTTPException(status_code=400, detail="Client record not found")
    return rows[0]


def _insert_incident_row(
    *,
    client_id: str,
    reported_by_uid: str,
    description: str,
    reported_at: datetime,
    sla_deadline: datetime,
) -> dict[str, Any]:
    payload = {
        "client_id": client_id,
        "reported_by_user_id": reported_by_uid,
        "description": description[:4000],
        "reported_at": reported_at.isoformat(),
        "sla_deadline": sla_deadline.isoformat(),
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_incident_reports",
        headers=_headers(),
        params={"select": "*"},
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.error("incident_report insert: %s %s", r.status_code, r.text[:500])
        raise HTTPException(status_code=502, detail="Could not log incident report") from None
    rows = r.json()
    if not rows:
        raise HTTPException(status_code=502, detail="Incident insert returned no row")
    return rows[0]


def _patch_incident_statuses(incident_id: str, patch: dict[str, Any]) -> None:
    """Best-effort status update — never raises (the incident is already logged)."""
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/client_incident_reports",
            headers=_headers(),
            params={"id": f"eq.{incident_id}"},
            json=patch,
            timeout=20.0,
        )
        if r.status_code >= 400:
            logger.warning("incident status patch failed: %s %s", r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("incident status patch raised: %s", e)


def _insert_support_ticket_mirror(
    *,
    case_id: str,
    company: str,
    domain: str,
    description: str,
    ceo_profile_id: str,
) -> str | None:
    subject = f"[{case_id}] Client-reported incident — {company}"
    body = (
        f"Company: {company}\n"
        f"Domain: {domain}\n"
        f"Case id: {case_id}\n\n"
        f"Client description:\n{description or '(no additional details provided)'}"
    )
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/crm_support_tickets",
        headers=_headers(),
        params={"select": "id"},
        json={
            "subject": subject[:200],
            "body": body,
            "priority": "high",
            "requester_id": ceo_profile_id,
        },
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.warning("incident ticket mirror insert failed: %s %s", r.status_code, r.text[:300])
        return None
    rows = r.json() or []
    if not rows:
        return None
    tid = rows[0].get("id")
    return str(tid) if tid else None


def _confirmation_html(
    *,
    company: str,
    case_id: str,
    sla_deadline_iso: str,
    sla_minutes: int,
) -> str:
    return f"""<!doctype html>
<html><body style="font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0F1117; color:#F2F2F5; padding:24px;">
  <h2 style="margin:0 0 12px;">Incident report received — HAWK is on it</h2>
  <p style="margin:0 0 12px;">Hi {_esc(company)},</p>
  <p style="margin:0 0 12px;">We have logged your incident report and our response team has been paged.</p>
  <table style="border-collapse:collapse; width:100%; max-width:520px; margin:16px 0;">
    <tr><td style="padding:8px 0; color:#9090A8;">Case id</td><td style="padding:8px 0; font-weight:600;">{_esc(case_id)}</td></tr>
    <tr><td style="padding:8px 0; color:#9090A8;">Reported at</td><td style="padding:8px 0;">{_esc(datetime.now(timezone.utc).isoformat())}</td></tr>
    <tr><td style="padding:8px 0; color:#9090A8;">First-response SLA</td><td style="padding:8px 0;">{sla_minutes} minutes — by {_esc(sla_deadline_iso)}</td></tr>
  </table>
  <p style="margin:0 0 12px;">You do not need to do anything else right now. If you have more context (timeline, affected systems, suspicious emails), reply to this thread and we'll attach it to the case.</p>
  <p style="margin:0; color:#9090A8; font-size:12px;">HAWK Security — <a href="https://securedbyhawk.com/portal" style="color:#00C48C; text-decoration:none;">portal</a></p>
</body></html>"""


def report_incident(
    *,
    uid: str,
    user_email: str,
    description: str,
) -> dict[str, Any]:
    """Full fan-out. Raises HTTPException for unrecoverable errors; soft-fails each side-effect."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    cid = get_client_id_for_portal_user(uid)
    if not cid:
        raise HTTPException(status_code=400, detail="No portal client linked to this account")

    client_ctx = _load_client_context(cid)
    company = (client_ctx.get("company_name") or client_ctx.get("domain") or "").strip() or "your organization"
    domain = (client_ctx.get("domain") or "").strip()

    now = datetime.now(timezone.utc)
    sla_minutes = max(5, DEFAULT_SLA_MINUTES)
    sla_deadline = now + timedelta(minutes=sla_minutes)

    row = _insert_incident_row(
        client_id=cid,
        reported_by_uid=uid,
        description=description,
        reported_at=now,
        sla_deadline=sla_deadline,
    )
    incident_id = str(row["id"])
    case_id = _short_case_id(incident_id)

    # --- SMS the CEO. Graceful when OpenPhone isn't configured.
    sms_msg = (
        f"🚨 HAWK — Client incident reported\n"
        f"Case: {case_id}\n"
        f"Company: {company}\n"
        f"Domain: {domain or '—'}\n"
        f"SLA: {sla_minutes}m (by {sla_deadline.isoformat()})"
    )
    try:
        sms_res = send_ceo_sms(sms_msg)
    except Exception as e:
        logger.exception("incident ceo sms raised: %s", e)
        sms_res = {"skipped": True, "reason": "exception"}
    ceo_sms_status = "sent" if sms_res.get("ok") else f"skipped:{sms_res.get('reason', 'unknown')}"

    # --- Email the client. Graceful when Resend isn't configured.
    email_status = "skipped:no_user_email"
    if user_email and "@" in user_email:
        try:
            email_res = send_resend(
                to_email=user_email,
                subject=f"HAWK incident report received — {case_id}",
                html=_confirmation_html(
                    company=company,
                    case_id=case_id,
                    sla_deadline_iso=sla_deadline.isoformat(),
                    sla_minutes=sla_minutes,
                ),
                tags=[{"name": "category", "value": "incident_report_confirm"}],
            )
            email_status = "skipped:no_resend_key" if email_res.get("skipped") else "sent"
        except httpx.HTTPError as e:
            logger.exception("incident client email raised: %s", e)
            email_status = "error:resend_http"
        except Exception as e:
            logger.exception("incident client email raised: %s", e)
            email_status = "error:unknown"

    # --- Mirror as internal support ticket. Wrap every network call so a
    # transport-level exception (httpx.TimeoutException / ConnectError) can't
    # crash the endpoint after the incident row is already persisted.
    ticket_id: str | None = None
    try:
        ceo_pid = _ceo_profile_id()
        if ceo_pid:
            ticket_id = _insert_support_ticket_mirror(
                case_id=case_id,
                company=company,
                domain=domain,
                description=description,
                ceo_profile_id=ceo_pid,
            )
    except Exception as e:
        logger.exception("incident support ticket mirror raised: %s", e)

    _patch_incident_statuses(
        incident_id,
        {
            "ceo_sms_status": ceo_sms_status,
            "client_email_status": email_status,
            "support_ticket_id": ticket_id,
        },
    )

    return {
        "ok": True,
        "incident_id": incident_id,
        "case_id": case_id,
        "reported_at": now.isoformat(),
        "sla_deadline": sla_deadline.isoformat(),
        "sla_minutes": sla_minutes,
        "ceo_sms_status": ceo_sms_status,
        "client_email_status": email_status,
        "support_ticket_id": ticket_id,
    }
