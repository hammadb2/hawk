"""ARIA Phase 18 — WhatsApp webhook + management endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from routers.crm_ai_command import require_supabase_uid, _require_ai_access, _get_profile, _get_role_permissions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/ai/whatsapp", tags=["aria-whatsapp"])


# ── Webhook verification (GET) ──────────────────────────────────────────

@router.get("/webhook")
def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge"),
) -> Any:
    """WhatsApp webhook verification (challenge-response)."""
    import os

    verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "aria-hawk-verify").strip()
    if mode == "subscribe" and token == verify_token:
        return int(challenge) if challenge and challenge.isdigit() else challenge
    raise HTTPException(status_code=403, detail="Verification failed")


# ── Webhook incoming messages (POST) ────────────────────────────────────

@router.post("/webhook")
async def incoming_webhook(request: Request) -> dict[str, str]:
    """Receive incoming WhatsApp messages."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    from services.aria_whatsapp import handle_incoming_message

    result = handle_incoming_message(payload)
    logger.info("WhatsApp webhook processed: %s", result)
    return {"status": "ok"}


# ── Queue management ────────────────────────────────────────────────────

@router.get("/queue")
def get_queue(
    status: str = "pending",
    uid: str = Depends(require_supabase_uid),
) -> list[dict[str, Any]]:
    """Get WhatsApp reply approval queue."""
    prof = _require_ai_access(uid)
    perms = _get_role_permissions(prof)
    if not perms.get("prospect_data"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from services.aria_whatsapp import get_wa_queue

    return get_wa_queue(status=status)


class SendBody(BaseModel):
    phone: str
    message: str


@router.post("/send")
def send_message(
    body: SendBody,
    uid: str = Depends(require_supabase_uid),
) -> dict[str, Any]:
    """Send a WhatsApp message (requires confirmation)."""
    prof = _require_ai_access(uid)
    perms = _get_role_permissions(prof)
    if not perms.get("prospect_data"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from services.aria_whatsapp import send_text_message

    return send_text_message(body.phone, body.message)


@router.post("/queue/{queue_id}/approve")
def approve_queued(
    queue_id: str,
    uid: str = Depends(require_supabase_uid),
) -> dict[str, Any]:
    """Approve and send a queued WhatsApp reply."""
    prof = _require_ai_access(uid)
    perms = _get_role_permissions(prof)
    if not perms.get("prospect_data"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from services.aria_whatsapp import approve_and_send

    return approve_and_send(queue_id)
