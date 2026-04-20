"""OpenPhone SMS — CRM alerts (replaces Twilio WhatsApp)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENPHONE_API_KEY = os.environ.get("OPENPHONE_API_KEY", "").strip()
OPENPHONE_FROM_NUMBER = os.environ.get("OPENPHONE_FROM_NUMBER", "").strip()
OPENPHONE_BASE_URL = os.environ.get("OPENPHONE_BASE_URL", "https://api.openphone.com/v1").rstrip("/")


def _normalize_e164(raw: str) -> str:
    s = raw.strip().replace("whatsapp:", "")
    if s.startswith("+"):
        return "+" + "".join(c for c in s[1:] if c.isdigit())
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"


def send_sms(to: str, message: str) -> dict[str, Any]:
    """
    Send SMS via OpenPhone. `to` may be E.164 or legacy whatsapp:+ form.
    Returns {"ok": True, ...} on success, or {"skipped": True, ...} when skipped / failed softly.
    """
    if not OPENPHONE_API_KEY or not OPENPHONE_FROM_NUMBER:
        logger.warning("OpenPhone not configured — skipping SMS")
        return {"skipped": True, "reason": "openphone_not_configured"}

    to_e164 = _normalize_e164(to)
    if not to_e164:
        return {"skipped": True, "reason": "empty_to"}

    headers = {
        "Authorization": f"Bearer {OPENPHONE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "from": OPENPHONE_FROM_NUMBER,
        "to": [to_e164],
        "content": message[:1600],
    }

    url = f"{OPENPHONE_BASE_URL}/messages"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=headers, json=payload)
    except Exception as e:
        logger.exception("OpenPhone SMS request failed: %s", e)
        return {"skipped": True, "reason": "request_error"}

    if r.status_code in (200, 201, 202):
        try:
            data = r.json()
        except Exception:
            data = {}
        return {"ok": True, "data": data}

    logger.error("OpenPhone SMS failed: %s %s", r.status_code, r.text[:500])
    return {"skipped": True, "reason": "openphone_http_error", "status_code": r.status_code}


def send_ceo_sms(message: str) -> dict[str, Any]:
    ceo_number = os.environ.get("CRM_CEO_PHONE_E164", "+18259458282").strip()
    return send_sms(ceo_number, message)


def send_client_sms(to: str, message: str) -> dict[str, Any]:
    return send_sms(to, message)


def format_stale_deal_message(
    *,
    company: str,
    domain: str,
    stage: str,
    rep_name: str,
    prospect_url: str,
) -> str:
    return (
        "⚠️ HAWK — Stale Deal\n"
        f"{company} has had no activity for 48 hours.\n"
        f"Domain: {domain}\n"
        f"Stage: {stage}\n"
        f"Rep: {rep_name}\n"
        f"View: {prospect_url}"
    )


def format_aging_deal_message(
    *,
    company: str,
    domain: str,
    stage: str,
    rep_name: str,
    prospect_url: str,
    days_inactive: int,
) -> str:
    return (
        "⏱️ HAWK — Aging pipeline\n"
        f"{company} has had no activity for {days_inactive}+ days.\n"
        f"Domain: {domain}\n"
        f"Stage: {stage}\n"
        f"Rep: {rep_name}\n"
        f"View: {prospect_url}"
    )


def format_hot_lead_message(
    *,
    company: str,
    domain: str,
    hawk_score: int | str,
    industry: str | None,
    prospect_url: str,
) -> str:
    ind = industry or "—"
    return (
        "🦅 HAWK Alert — Hot Lead\n"
        f"{company} replied to ARIA.\n"
        f"Domain: {domain}\n"
        f"HAWK Score: {hawk_score}\n"
        f"Industry: {ind}\n"
        f"View in CRM: {prospect_url}"
    )


def format_aria_reply_rep_message(
    *,
    company: str,
    first_name: str | None,
    crm_base_url: str,
) -> str:
    fn = (first_name or "").strip() or "Someone"
    base = crm_base_url.rstrip("/")
    return (
        f"New ARIA reply. {company}. {fn} replied to your email. "
        f"Login: {base}/crm"
    )


def format_aria_reply_ceo_message(
    *,
    company: str,
    score: int | str,
    rep_name: str,
) -> str:
    return f"ARIA reply. {company} scored {score}/100. Assigned to {rep_name}."


# Legacy aliases kept so older imports keep working.
format_charlotte_reply_rep_message = format_aria_reply_rep_message
format_charlotte_reply_ceo_message = format_aria_reply_ceo_message
