"""CRM scale features: VA reply queue actions, health dashboard (authenticated)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from config import CRM_PUBLIC_BASE_URL
from routers.crm_auth import require_supabase_uid
from services.crm_charlotte_quality import run_charlotte_quality_check
from services.crm_twilio import send_whatsapp
from services.crm_va_escalation import run_va_reply_escalation
from services.crm_onboarding_sequences import run_shield_onboarding_sequences
from services.scanner_health_service import run_scanner_health_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm", tags=["crm-scale"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
CRM_CEO_WHATSAPP_E164 = os.environ.get("CRM_CEO_WHATSAPP_E164", "").strip() or "+18259458282"
VA_WHATSAPP_NUMBER = os.environ.get("VA_WHATSAPP_NUMBER", "").strip()
CAL_COM_BOOKING_URL = os.environ.get("CAL_COM_BOOKING_URL", "https://cal.com/hawk").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _profile_role(uid: str) -> str | None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "role", "limit": "1"},
        timeout=15.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    return str(rows[0].get("role") or "")


def _require_va_dashboard(uid: str) -> None:
    role = _profile_role(uid)
    if role not in ("ceo", "hos", "team_lead", "sales_rep"):
        raise HTTPException(status_code=403, detail="Insufficient role")


class VaActionBody(BaseModel):
    prospect_id: str = Field(..., min_length=1)
    action: Literal["book_call", "not_interested", "follow_up"]


@router.get("/pending-replies")
def list_pending_replies(uid: str = Depends(require_supabase_uid)):
    """Prospects with reply_received_at set and VA not yet actioned."""
    _require_va_dashboard(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={
            "reply_received_at": "not.is.null",
            "va_actioned_at": "is.null",
            "select": "id,domain,company_name,contact_name,contact_email,industry,hawk_score,reply_received_at,created_at",
            "order": "reply_received_at.asc",
            "limit": "200",
        },
        timeout=25.0,
    )
    r.raise_for_status()
    rows = r.json()
    return {"ok": True, "prospects": rows}


@router.post("/va/action")
def va_action(body: VaActionBody, uid: str = Depends(require_supabase_uid)):
    _require_va_dashboard(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={"id": f"eq.{body.prospect_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    pr.raise_for_status()
    rows = pr.json()
    if not rows:
        raise HTTPException(status_code=404, detail="Prospect not found")
    p = rows[0]
    reply_at = p.get("reply_received_at")
    now = datetime.now(timezone.utc)
    minutes: int | None = None
    if reply_at:
        try:
            rt = datetime.fromisoformat(str(reply_at).replace("Z", "+00:00"))
            minutes = int((now - rt).total_seconds() // 60)
        except Exception:
            minutes = None

    patch: dict[str, Any] = {
        "va_actioned_at": now.isoformat(),
        "reply_response_minutes": minutes,
    }
    if body.action == "follow_up":
        patch["va_snooze_until"] = (now + timedelta(hours=24)).isoformat()
    if body.action == "not_interested":
        patch["stage"] = "lost"
        dom = p.get("domain")
        em = p.get("contact_email")
        if dom:
            try:
                httpx.post(
                    f"{SUPABASE_URL}/rest/v1/suppressions",
                    headers=_sb_headers(),
                    json={"domain": dom, "email": em or "", "reason": "manual"},
                    timeout=15.0,
                )
            except Exception:
                logger.exception("suppression insert")

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={"id": f"eq.{body.prospect_id}"},
        json=patch,
        timeout=20.0,
    ).raise_for_status()

    base = CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com"
    book_url = CAL_COM_BOOKING_URL
    if body.action == "book_call":
        # Pre-filled Cal.com query params (best-effort)
        q = f"?name={p.get('contact_name') or ''}&email={p.get('contact_email') or ''}"
        return {"ok": True, "cal_url": f"{book_url}{q}", "crm_url": f"{base}/crm/prospects/{body.prospect_id}"}

    return {"ok": True, "crm_url": f"{base}/crm/prospects/{body.prospect_id}"}


@router.get("/health-dashboard")
def health_dashboard(uid: str = Depends(require_supabase_uid)):
    _require_va_dashboard(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/charlotte_runs",
        headers=_sb_headers(),
        params={"select": "*", "order": "created_at.desc", "limit": "1"},
        timeout=20.0,
    )
    cr.raise_for_status()
    last_run = cr.json()[0] if cr.json() else None

    pend = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={
            "reply_received_at": "not.is.null",
            "va_actioned_at": "is.null",
            "select": "id,reply_received_at",
            "limit": "500",
        },
        timeout=20.0,
    )
    pend.raise_for_status()
    pending_n = len(pend.json())

    health = httpx.get(
        f"{SUPABASE_URL}/rest/v1/scanner_health_logs",
        headers=_sb_headers(),
        params={"select": "*", "order": "checked_at.desc", "limit": "1"},
        timeout=15.0,
    )
    last_scan_health = health.json()[0] if health.status_code == 200 and health.json() else None

    return {
        "ok": True,
        "charlotte_last_run": last_run,
        "replies_unhandled": pending_n,
        "scanner_health_last": last_scan_health,
    }


# Cron jobs — same prefix as crm_cron.router; mounted explicitly from main so /api/crm/cron/* is always registered with crm_scale.
CRON_SECRET = (
    os.environ.get("HAWK_CRM_CRON_SECRET", "").strip()
    or os.environ.get("HAWK_CRON_SECRET", "").strip()
    or os.environ.get("CRON_SECRET", "").strip()
)


def _require_cron_secret(x_cron_secret: str | None) -> None:
    if not CRON_SECRET:
        logger.warning("Cron secret not set (HAWK_CRM_CRON_SECRET / HAWK_CRON_SECRET / CRON_SECRET) — rejecting")
        raise HTTPException(status_code=503, detail="Cron not configured")
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


cron_routes = APIRouter(prefix="/api/crm/cron", tags=["crm-cron"])


@cron_routes.post("/scanner-health")
def cron_scanner_health(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Queue depth + failure logging + CEO WhatsApp if thresholds exceeded."""
    _require_cron_secret(x_cron_secret)
    return run_scanner_health_check()


@cron_routes.post("/va-reply-escalation")
def cron_va_reply_escalation(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """CEO WhatsApp if reply unhandled > 30 min."""
    _require_cron_secret(x_cron_secret)
    return run_va_reply_escalation()


@cron_routes.post("/charlotte-quality-check")
def cron_charlotte_quality(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Charlotte email QA metrics; alert CEO if out of range."""
    _require_cron_secret(x_cron_secret)
    return run_charlotte_quality_check()


@cron_routes.post("/onboarding-sequences")
def cron_onboarding_sequences(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Shield Day 1 / 3 / 7 — schedule daily ~14:00 UTC (cron-job.org)."""
    _require_cron_secret(x_cron_secret)
    return run_shield_onboarding_sequences()
