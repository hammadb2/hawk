"""CRM inbound webhooks — email engagement events (Smartlead / Charlotte / custom) into Supabase."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/webhooks", tags=["crm-webhooks"])

WEBHOOK_SECRET = os.environ.get("CRM_EMAIL_WEBHOOK_SECRET", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def normalize_domain(raw: str) -> str:
    d = raw.strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix) :]
    d = d.split("/")[0].split("?")[0].strip()
    if not d:
        return ""
    # strip accidental email
    if "@" in d:
        d = d.split("@")[-1]
    d = re.sub(r"^www\.", "", d)
    return d


class EmailEventIn(BaseModel):
    """Payload for POST /api/crm/webhooks/email-events — at least one of prospect_id or domain."""

    prospect_id: Optional[str] = None
    domain: Optional[str] = None
    subject: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    sequence_step: Optional[int] = None
    source: str = Field(default="smartlead", description="smartlead | charlotte | webhook | manual")
    external_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("domain", mode="before")
    @classmethod
    def empty_domain_to_none(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @field_validator("prospect_id", mode="before")
    @classmethod
    def empty_pid_to_none(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


def _require_webhook_secret(x_secret: str | None) -> None:
    if not WEBHOOK_SECRET:
        logger.warning("CRM_EMAIL_WEBHOOK_SECRET not set — rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")
    if x_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _resolve_prospect_id(body: EmailEventIn) -> str:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    headers = _sb_headers()
    if body.prospect_id:
        url = f"{SUPABASE_URL}/rest/v1/prospects"
        r = httpx.get(
            url,
            headers=headers,
            params={"id": f"eq.{body.prospect_id}", "select": "id", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise HTTPException(status_code=404, detail="Prospect not found")
        return str(rows[0]["id"])

    if body.domain:
        nd = normalize_domain(body.domain)
        if not nd:
            raise HTTPException(status_code=400, detail="Invalid domain")
        url = f"{SUPABASE_URL}/rest/v1/prospects"
        r = httpx.get(
            url,
            headers=headers,
            params={
                "domain": f"eq.{nd}",
                "select": "id",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No prospect for domain {nd}")
        return str(rows[0]["id"])

    raise HTTPException(status_code=400, detail="Provide prospect_id or domain")


@router.post("/email-events")
def ingest_email_event(
    body: EmailEventIn,
    x_crm_webhook_secret: str | None = Header(default=None, alias="X-CRM-Webhook-Secret"),
):
    """
    Record an email engagement row for a prospect (outbound tool → HAWK API → Supabase).

    **Auth:** header `X-CRM-Webhook-Secret` must match `CRM_EMAIL_WEBHOOK_SECRET`.

    **Match prospect:** send `prospect_id` (uuid) **or** `domain` (we pick the newest prospect with that domain).

    **Idempotency:** optional `external_id` (per prospect). Duplicate posts return the existing row.
    """
    _require_webhook_secret(x_crm_webhook_secret)

    pid = _resolve_prospect_id(body)
    headers = _sb_headers()

    if body.external_id and body.external_id.strip():
        ext = body.external_id.strip()
        chk = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospect_email_events",
            headers=headers,
            params={
                "prospect_id": f"eq.{pid}",
                "external_id": f"eq.{ext}",
                "select": "id,created_at",
                "limit": "1",
            },
            timeout=20.0,
        )
        chk.raise_for_status()
        existing = chk.json()
        if existing:
            return {"ok": True, "duplicate": True, "id": existing[0]["id"]}

    row = {
        "prospect_id": pid,
        "subject": body.subject,
        "sent_at": body.sent_at.isoformat() if body.sent_at else None,
        "opened_at": body.opened_at.isoformat() if body.opened_at else None,
        "clicked_at": body.clicked_at.isoformat() if body.clicked_at else None,
        "replied_at": body.replied_at.isoformat() if body.replied_at else None,
        "sequence_step": body.sequence_step,
        "source": (body.source or "webhook")[:64],
        "external_id": body.external_id.strip() if body.external_id else None,
        "metadata": body.metadata or {},
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/prospect_email_events",
        headers=headers,
        json=row,
        timeout=20.0,
    )
    if r.status_code == 409:
        logger.info("email event conflict prospect=%s external_id=%s", pid, body.external_id)
        raise HTTPException(status_code=409, detail="Conflict — duplicate external_id")
    r.raise_for_status()
    out = r.json()
    inserted = out[0] if isinstance(out, list) and out else out
    eid = inserted.get("id") if isinstance(inserted, dict) else None
    return {"ok": True, "id": eid, "prospect_id": pid}


@router.get("/email-events/health")
def webhook_health():
    """Whether the email webhook is configured (no secrets returned)."""
    return {
        "configured": bool(WEBHOOK_SECRET and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        "has_secret": bool(WEBHOOK_SECRET),
        "has_supabase": bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
    }
