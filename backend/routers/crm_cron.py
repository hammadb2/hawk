"""CRM scheduled jobs — aging reminders (WhatsApp stub), called by Vercel/Railway cron with secret header."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/cron", tags=["crm-cron"])

# Prefer CRM-specific secret, then HAWK_CRON_SECRET, then CRON_SECRET (Railway).
CRON_SECRET = (
    os.environ.get("HAWK_CRM_CRON_SECRET", "").strip()
    or os.environ.get("HAWK_CRON_SECRET", "").strip()
    or os.environ.get("CRON_SECRET", "").strip()
)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _require_secret(x_cron_secret: str | None) -> None:
    if not CRON_SECRET:
        logger.warning("Cron secret not set (HAWK_CRM_CRON_SECRET / HAWK_CRON_SECRET / CRON_SECRET) — rejecting")
        raise HTTPException(status_code=503, detail="Cron not configured")
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/aging")
def aging_hourly(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    Hourly job: find prospects inactive ~10 days for WhatsApp (stub).
    Kanban borders refresh client-side every 60s; this endpoint is for rep nudges.
    """
    _require_secret(x_cron_secret)

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {
            "ok": True,
            "mode": "stub",
            "message": "Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to scan prospects for 10-day WhatsApp alerts.",
            "whatsapp_sent": 0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    cutoff_iso = cutoff.isoformat()
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    url = f"{SUPABASE_URL}/rest/v1/prospects"
    params = {
        "select": "id,domain,assigned_rep_id,last_activity_at,stage",
        "last_activity_at": f"lt.{cutoff_iso}",
    }
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=30.0)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        logger.exception("aging cron supabase fetch failed: %s", e)
        raise HTTPException(status_code=502, detail="Supabase fetch failed") from e

    candidates = [x for x in rows if x.get("stage") not in ("lost", "closed_won")]
    for row in candidates:
        logger.info("aging candidate prospect=%s rep=%s", row.get("id"), row.get("assigned_rep_id"))

    return {"ok": True, "mode": "live", "candidates": len(candidates), "whatsapp_sent": 0}
