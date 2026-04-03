"""Daily Charlotte email quality check from charlotte_emails rows (CEO alert if out of range)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from config import CRM_CEO_PHONE_E164
from services.crm_openphone import send_sms

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


def run_charlotte_quality_check() -> dict:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "Supabase not configured"}
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/charlotte_emails",
        headers=_headers(),
        params={
            "created_at": f"gte.{since}",
            "select": "word_count,has_dashes,has_bullets,contains_domain,contains_score",
            "limit": "2000",
        },
        timeout=45.0,
    )
    r.raise_for_status()
    rows = r.json() or []
    if not rows:
        return {"ok": True, "checked": 0, "alert": False}

    n = len(rows)
    words = [x.get("word_count") or 0 for x in rows]
    avg = sum(words) / max(1, n)
    dash_pct = sum(1 for x in rows if x.get("has_dashes")) / n * 100
    bull_pct = sum(1 for x in rows if x.get("has_bullets")) / n * 100
    dom_pct = sum(1 for x in rows if x.get("contains_domain")) / n * 100
    score_pct = sum(1 for x in rows if x.get("contains_score")) / n * 100

    bad = (
        avg < 80
        or avg > 100
        or dash_pct > 0
        or bull_pct > 0
        or dom_pct < 100
        or score_pct < 100
    )
    if bad:
        msg = (
            "Charlotte email quality check failed.\n"
            f"Avg words: {avg:.1f} (target 80–100)\n"
            f"Dashes: {dash_pct:.0f}% Bullets: {bull_pct:.0f}%\n"
            f"Domain in copy: {dom_pct:.0f}% Score in copy: {score_pct:.0f}%"
        )
        try:
            send_sms(CRM_CEO_PHONE_E164 or "+18259458282", msg)
        except Exception:
            logger.exception("CEO quality WhatsApp")

    return {
        "ok": True,
        "checked": n,
        "avg_word_count": avg,
        "alert": bad,
    }
