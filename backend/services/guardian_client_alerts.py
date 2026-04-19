"""Resend + SMS alerts for Guardian threats and large ARIA health score moves."""

from __future__ import annotations

import html
import json
import logging
import os
from typing import Any

import httpx

from config import SUPABASE_URL
from services.crm_openphone import send_ceo_sms, send_client_sms
from services.crm_portal_email import send_resend

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

THREAT_SEVERITIES = frozenset({"high", "critical"})
CREDENTIAL_EVENTS = frozenset(
    {
        "credential_phishing",
        "password_field_external",
        "suspicious_login_form",
        "fake_oauth",
        "homograph_domain",
    }
)


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _client_portal_email(client_id: str) -> str | None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_headers(),
        params={"client_id": f"eq.{client_id}", "select": "email", "limit": "1"},
        timeout=15.0,
    )
    if r.status_code >= 400:
        return None
    rows = r.json() or []
    if not rows:
        return None
    em = (rows[0].get("email") or "").strip().lower()
    return em if em and "@" in em else None


def _notify_crm_users_for_client(*, title: str, message: str, link: str) -> None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return
    h = _headers()
    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=h,
        params={"select": "id", "role": "in.(ceo,hos)", "limit": "20"},
        timeout=15.0,
    )
    if pr.status_code >= 400:
        return
    for row in pr.json() or []:
        uid = row.get("id")
        if not uid:
            continue
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/notifications",
            headers={**h, "Prefer": "return=minimal"},
            json={
                "user_id": uid,
                "title": title[:200],
                "message": message[:2000],
                "type": "warning",
                "link": link[:500],
            },
            timeout=15.0,
        )


def on_guardian_threat_event(
    *,
    client_id: str,
    event_type: str,
    severity: str,
    details: dict[str, Any],
    company_name: str | None = None,
) -> None:
    """CEO SMS, client SMS (contact_phone), client email, CRM notifications when appropriate."""
    sev = (severity or "medium").lower()
    et = (event_type or "").lower()
    is_cred = et in CREDENTIAL_EVENTS
    cred_sev_ok = is_cred and sev in ("medium", "high", "critical")
    if sev not in THREAT_SEVERITIES and not cred_sev_ok:
        return

    if not SUPABASE_URL or not SERVICE_KEY:
        return

    h = _headers()
    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=h,
        params={
            "id": f"eq.{client_id}",
            "select": "id,company_name,domain,contact_phone",
            "limit": "1",
        },
        timeout=15.0,
    )
    if cr.status_code >= 400:
        return
    crows = cr.json() or []
    if not crows:
        return
    c = crows[0]
    label = company_name or c.get("company_name") or c.get("domain") or client_id
    summary = f"{label}: Guardian {et} ({sev})"

    send_ceo_sms(f"HAWK Guardian — {summary}. Check CRM → Guardian.")

    phone = (c.get("contact_phone") or "").strip()
    if phone:
        send_client_sms(
            phone,
            f"HAWK Security: unusual sign-in or login page detected for {label}. "
            f"If you did not expect this, contact support. Do not enter passwords on unfamiliar pages.",
        )

    to_email = _client_portal_email(client_id)
    if to_email:
        try:
            send_resend(
                to_email=to_email,
                subject=f"HAWK Guardian alert — {label}",
                html=(
                    f"<p>We detected a potential security issue related to your account "
                    f"({details.get('page_url') or details.get('url') or 'web'}).</p>"
                    f"<p><b>Type:</b> {et}<br/><b>Severity:</b> {sev}</p>"
                    "<p>If you did not initiate this activity, reply to this email or call your HAWK contact.</p>"
                ),
            )
        except Exception:
            logger.exception("Guardian client email failed client_id=%s", client_id)

    _notify_crm_users_for_client(
        title=f"Guardian: {label}",
        message=f"{et} — {sev}. Review Guardian dashboard.",
        link="/crm/guardian",
    )


def send_health_score_change_email(
    *,
    client_id: str,
    company_name: str,
    old_score: int,
    new_score: int,
    factors: dict[str, Any],
) -> None:
    """Email client when ARIA health score moves by more than 5 points."""
    to_email = _client_portal_email(client_id)
    if not to_email:
        return
    delta = new_score - old_score
    try:
        factors_html = html.escape(json.dumps(factors, default=str)[:4000])
        send_resend(
            to_email=to_email,
            subject=f"HAWK — account health score update ({company_name})",
            html=(
                f"<p>Your HAWK account health score changed from <b>{old_score}</b> to <b>{new_score}</b> "
                f"({delta:+d}).</p>"
                f"<p>This reflects scan activity, engagement, and risk signals we track for your organization.</p>"
                f"<p><small>Factors snapshot:</small></p><pre style=\"white-space:pre-wrap;font-size:12px\">{factors_html}</pre>"
                "<p>Questions? Open your HAWK portal or reply to this message.</p>"
            ),
        )
    except Exception:
        logger.exception("health score change email failed client_id=%s", client_id)
