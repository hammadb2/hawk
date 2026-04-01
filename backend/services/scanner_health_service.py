"""Hourly scanner health: Redis queue depth, failure rate from logs, WhatsApp CEO on thresholds."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import CRM_CEO_WHATSAPP_E164
from services.crm_twilio import send_whatsapp

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
QUEUE_ALERT = 5000
FAILURE_RATE_ALERT = 10.0


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _redis_queue_depth() -> int | None:
    if not REDIS_URL:
        return None
    try:
        import redis

        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        # arq default list
        return int(r.llen("arq:queue") or 0)
    except Exception as e:
        logger.warning("redis queue depth: %s", e)
        return None


def _failure_rate_last_hour() -> float | None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/scanner_failures",
            headers=_sb_headers(),
            params={
                "created_at": f"gte.{since}",
                "select": "id",
            },
            timeout=20.0,
        )
        r.raise_for_status()
        # approximate: failures in last hour / max(1, estimated jobs) — without job count use raw count
        n = len(r.json())
        return min(100.0, float(n))
    except Exception as e:
        logger.warning("failure rate fetch: %s", e)
        return None


def run_scanner_health_check() -> dict[str, Any]:
    depth = _redis_queue_depth()
    fail_pct = _failure_rate_last_hour()
    alert = False
    ceo_msg = ""
    num = CRM_CEO_WHATSAPP_E164 or "+18259458282"

    if depth is not None and depth > QUEUE_ALERT:
        alert = True
        ceo_msg = f"Scanner queue depth high: {depth} (threshold {QUEUE_ALERT})."
    if fail_pct is not None and fail_pct > FAILURE_RATE_ALERT:
        alert = True
        ceo_msg = (ceo_msg + "\n" if ceo_msg else "") + f"Scanner failure signal high (approx): {fail_pct:.1f}."

    row = {
        "queue_depth": depth,
        "avg_completion_seconds": None,
        "failure_rate_pct": fail_pct,
        "workers_active": None,
        "alert_sent": alert,
    }
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/scanner_health_logs",
                headers=_sb_headers(),
                json=row,
                timeout=20.0,
            ).raise_for_status()
        except Exception as e:
            logger.exception("scanner_health_logs insert: %s", e)

    if alert and ceo_msg:
        try:
            send_whatsapp(num, "HAWK Scanner health\n" + ceo_msg)
        except Exception:
            logger.exception("CEO scanner health WhatsApp")

    return {"ok": True, "queue_depth": depth, "failure_rate_pct": fail_pct, "alert_sent": alert}
