"""CRM inbound webhooks — email engagement events (Smartlead / Charlotte / custom) into Supabase."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from config import CRM_CEO_WHATSAPP_E164, CRM_PUBLIC_BASE_URL
from services.crm_twilio import format_hot_lead_message, send_whatsapp

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
    event_type: Optional[str] = Field(
        default=None,
        description="Optional: email_replied | email_opened (Charlotte / Smartlead)",
    )
    company_name: Optional[str] = None
    industry: Optional[str] = None

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


def _round_robin_rep_id() -> tuple[str | None, str | None]:
    """Returns (rep_id, whatsapp_e164) for next active sales_rep."""
    headers = _sb_headers()
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={
            "role": "eq.sales_rep",
            "status": "eq.active",
            "select": "id,whatsapp_number,last_assigned_at",
            "order": "last_assigned_at.asc.nullsfirst",
            "limit": "1",
        },
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None, None
    rid = str(rows[0]["id"])
    wa = rows[0].get("whatsapp_number")
    patch = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"id": f"eq.{rid}"},
        json={"last_assigned_at": datetime.now(timezone.utc).isoformat()},
        timeout=20.0,
    )
    patch.raise_for_status()
    return rid, (str(wa).strip() if wa else None)


def _create_prospect_charlotte(
    *,
    nd: str,
    stage: str,
    assigned_rep_id: str,
    company: str,
    industry: str | None,
) -> dict:
    headers = _sb_headers()
    row = {
        "domain": nd,
        "company_name": company,
        "industry": industry,
        "stage": stage,
        "source": "charlotte",
        "assigned_rep_id": assigned_rep_id,
        "hawk_score": 0,
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
    }
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/prospects", headers=headers, json=row, timeout=20.0)
    if r.status_code == 409:
        raise HTTPException(status_code=409, detail="Duplicate domain")
    r.raise_for_status()
    out = r.json()
    return out[0] if isinstance(out, list) and out else out


def _resolve_prospect_or_create(body: EmailEventIn) -> tuple[str, bool]:
    """
    Returns (prospect_id, created_new).
    Charlotte auto-create: email_replied / email_opened with no existing prospect for domain.
    """
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
        return str(rows[0]["id"]), False

    if not body.domain:
        raise HTTPException(status_code=400, detail="Provide prospect_id or domain")

    nd = normalize_domain(body.domain)
    if not nd:
        raise HTTPException(status_code=400, detail="Invalid domain")

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
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
    if rows:
        return str(rows[0]["id"]), False

    md = body.metadata or {}
    et = (body.event_type or md.get("event_type") or "").lower()
    is_reply = body.replied_at is not None or et in ("email_replied", "reply", "replied")
    is_open = (
        not is_reply
        and (body.opened_at is not None or et in ("email_opened", "open", "opened"))
    )

    if not is_reply and not is_open:
        raise HTTPException(status_code=404, detail=f"No prospect for domain {nd}")

    rep_id, rep_wa = _round_robin_rep_id()
    if not rep_id:
        raise HTTPException(status_code=503, detail="No active sales_rep for round-robin")

    stage = "replied" if is_reply else "scanned"
    company = (body.company_name or md.get("company_name") or nd.split(".")[0].title())[:200]
    industry = body.industry or md.get("industry")

    pr = _create_prospect_charlotte(
        nd=nd,
        stage=stage,
        assigned_rep_id=rep_id,
        company=company,
        industry=industry,
    )
    pid = str(pr["id"])

    base = CRM_PUBLIC_BASE_URL
    prospect_url = f"{base}/crm/prospects/{pid}"
    msg = format_hot_lead_message(
        company=company,
        domain=nd,
        hawk_score=pr.get("hawk_score", 0) or 0,
        industry=industry,
        prospect_url=prospect_url,
    )
    if rep_wa:
        try:
            send_whatsapp(rep_wa, msg)
        except Exception:
            logger.exception("WhatsApp to rep failed")
    # CEO alert on positive reply only (spec: every reply, regardless of assignment)
    if CRM_CEO_WHATSAPP_E164 and is_reply:
        try:
            send_whatsapp(CRM_CEO_WHATSAPP_E164, msg)
        except Exception:
            logger.exception("WhatsApp to CEO failed")

    return pid, True


@router.post("/email-events")
def ingest_email_event(
    body: EmailEventIn,
    x_crm_webhook_secret: str | None = Header(default=None, alias="X-CRM-Webhook-Secret"),
):
    """
    Record an email engagement row for a prospect (outbound tool → HAWK API → Supabase).

    **Auth:** header `X-CRM-Webhook-Secret` must match `CRM_EMAIL_WEBHOOK_SECRET`.

    **Match prospect:** send `prospect_id` (uuid) **or** `domain` — if no prospect exists and the
    event is a Charlotte reply/open, a prospect is auto-created (round-robin assign).

    **Idempotency:** optional `external_id` (per prospect). Duplicate posts return the existing row.
    """
    _require_webhook_secret(x_crm_webhook_secret)

    pid, _created = _resolve_prospect_or_create(body)
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
            return {"ok": True, "duplicate": True, "id": existing[0]["id"], "prospect_id": pid}

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
