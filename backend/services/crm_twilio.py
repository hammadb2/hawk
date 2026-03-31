"""Twilio WhatsApp outbound — CRM alerts (Phase 1)."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()  # whatsapp:+1...


def _normalize_to_e164_digits(raw: str) -> str:
    s = raw.strip().replace("whatsapp:", "")
    if s.startswith("+"):
        return "+" + "".join(c for c in s[1:] if c.isdigit())
    return "".join(c for c in s if c.isdigit())


def send_whatsapp(to_number: str, body: str) -> dict:
    """
    Send a WhatsApp message via Twilio. `to_number` may be E.164 or whatsapp:+...
    Returns Twilio JSON or raises on HTTP error.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_WHATSAPP_FROM:
        logger.warning("Twilio not configured — skipping WhatsApp send")
        return {"skipped": True, "reason": "twilio_not_configured"}

    to = _normalize_to_e164_digits(to_number)
    if not to:
        return {"skipped": True, "reason": "empty_to"}

    if not to.startswith("+"):
        to = f"+{to}"

    from_wa = TWILIO_WHATSAPP_FROM
    if not from_wa.startswith("whatsapp:"):
        from_wa = f"whatsapp:{from_wa}"
    to_wa = to if to.startswith("whatsapp:") else f"whatsapp:{to}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    data = urlencode({"From": from_wa, "To": to_wa, "Body": body})

    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, auth=auth, content=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code >= 400:
            logger.error("Twilio WhatsApp failed: %s %s", r.status_code, r.text)
            r.raise_for_status()
        return r.json()


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
        f"{company} replied to Charlotte.\n"
        f"Domain: {domain}\n"
        f"HAWK Score: {hawk_score}\n"
        f"Industry: {ind}\n"
        f"View in CRM: {prospect_url}"
    )
