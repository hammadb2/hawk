"""ARIA Phase 18 — WhatsApp integration via WhatsApp Business Cloud API.

Send and receive WhatsApp messages through ARIA. Uses Meta's Cloud API.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "aria-hawk-verify").strip()

WA_API_BASE = "https://graph.facebook.com/v21.0"


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def send_text_message(to_phone: str, text: str) -> dict[str, Any]:
    """Send a WhatsApp text message.

    to_phone: E.164 format phone number (e.g. +15551234567)
    """
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        return {"error": "WhatsApp not configured (missing WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID)"}

    try:
        r = httpx.post(
            f"{WA_API_BASE}/{WHATSAPP_PHONE_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": to_phone.lstrip("+"),
                "type": "text",
                "text": {"body": text[:4096]},
            },
            timeout=20.0,
        )
        result = r.json()

        # Log message
        _log_wa_message("outbound", to_phone, text, result)

        if r.status_code < 400:
            return {"sent": True, "to": to_phone, "message_id": result.get("messages", [{}])[0].get("id")}
        return {"error": result.get("error", {}).get("message", f"HTTP {r.status_code}")}
    except Exception as exc:
        logger.exception("WhatsApp send failed: %s", exc)
        return {"error": str(exc)}


def send_template_message(
    to_phone: str,
    template_name: str,
    language: str = "en",
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send a WhatsApp template message (for initiating conversations)."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        return {"error": "WhatsApp not configured"}

    try:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if components:
            payload["template"]["components"] = components

        r = httpx.post(
            f"{WA_API_BASE}/{WHATSAPP_PHONE_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
        result = r.json()
        _log_wa_message("outbound_template", to_phone, template_name, result)

        if r.status_code < 400:
            return {"sent": True, "to": to_phone, "template": template_name}
        return {"error": result.get("error", {}).get("message", f"HTTP {r.status_code}")}
    except Exception as exc:
        logger.exception("WhatsApp template send failed: %s", exc)
        return {"error": str(exc)}


def handle_incoming_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Process an incoming WhatsApp webhook message.

    Classifies the message and drafts a response using ARIA.
    """
    entries = payload.get("entry", [])
    processed = 0

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])

            for msg in messages:
                from_phone = msg.get("from", "")
                msg_type = msg.get("type", "text")
                text = ""

                if msg_type == "text":
                    text = msg.get("text", {}).get("body", "")
                elif msg_type == "button":
                    text = msg.get("button", {}).get("text", "")
                else:
                    text = f"[{msg_type} message]"

                if text:
                    _log_wa_message("inbound", from_phone, text, msg)
                    _draft_reply(from_phone, text)
                    processed += 1

    return {"processed": processed}


def _draft_reply(from_phone: str, text: str) -> None:
    """Use ARIA to draft a reply to an incoming WhatsApp message."""
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        return

    try:
        from openai import OpenAI

        client = OpenAI(api_key=openai_key)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are ARIA, the WhatsApp assistant for Hawk Security. "
                        "Keep responses concise (under 300 characters when possible). "
                        "Be helpful, professional, and direct. "
                        "If the message is about security services, mention our tiers: "
                        "Starter $199/mo, Shield $997/mo, Enterprise $2,500/mo. "
                        "For booking calls, share the Cal.com link. "
                        "For urgent security issues, recommend calling directly."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=300,
            temperature=0.5,
        )

        reply = (response.choices[0].message.content or "").strip()
        if reply:
            # Store drafted reply for approval
            if SUPABASE_URL and SERVICE_KEY:
                httpx.post(
                    f"{SUPABASE_URL}/rest/v1/aria_whatsapp_queue",
                    headers=_sb(),
                    json={
                        "phone": from_phone,
                        "inbound_text": text,
                        "drafted_reply": reply,
                        "status": "pending",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    timeout=15.0,
                )
    except Exception as exc:
        logger.warning("WhatsApp reply draft failed: %s", exc)


def _log_wa_message(direction: str, phone: str, text: str, meta: Any) -> None:
    """Log WhatsApp message to database."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_whatsapp_messages",
            headers=_sb(),
            json={
                "direction": direction,
                "phone": phone,
                "content": text[:4096],
                "metadata": meta if isinstance(meta, dict) else {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("WhatsApp message logging failed: %s", exc)


def get_wa_queue(status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    """Get WhatsApp reply queue."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return []
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_whatsapp_queue",
        headers=_sb(),
        params={
            "status": f"eq.{status}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit),
        },
        timeout=20.0,
    )
    return r.json() if r.status_code < 400 else []


def approve_and_send(queue_id: str) -> dict[str, Any]:
    """Approve and send a queued WhatsApp reply.

    Uses an atomic conditional update to prevent duplicate sends from
    concurrent requests (TOCTOU race condition).
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"error": "Supabase not configured"}

    # Atomically claim the item: PATCH status from 'pending' → 'sending'
    # Only succeeds if item exists AND is still 'pending' (wins the race).
    claim = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/aria_whatsapp_queue",
        headers={**_sb(), "Prefer": "return=representation"},
        params={"id": f"eq.{queue_id}", "status": "eq.pending"},
        json={"status": "sending"},
        timeout=15.0,
    )
    claimed = claim.json() if claim.status_code < 400 else []
    if not claimed:
        return {"error": "Queue item not found or already processed"}

    item = claimed[0]

    # Send the message
    result = send_text_message(item["phone"], item["drafted_reply"])

    # Update final status (log warning on failure so item doesn't stay stuck in 'sending')
    new_status = "sent" if result.get("sent") else "failed"
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/aria_whatsapp_queue",
            headers=_sb(),
            params={"id": f"eq.{queue_id}"},
            json={"status": new_status, "sent_at": datetime.now(timezone.utc).isoformat()},
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("Failed to update queue status for %s: %s", queue_id, exc)

    return result
