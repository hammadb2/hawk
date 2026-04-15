"""Weekly VA scoring — runs Sunday night.

For each active VA, computes a weighted score from their daily reports for
the previous 7-day period and writes to va_scores.

total_score = output_volume * 0.30 + accuracy_score * 0.25 +
              reply_quality * 0.25 + booking_score * 0.20

standing: green (>= 80), yellow (>= 60), red (< 60)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Daily targets for a single VA (used to normalise to 0-100 scale)
TARGET_EMAILS = 400       # emails per day
TARGET_REPLIES = 14       # replies per day
TARGET_POSITIVE = 5       # positive replies per day
TARGET_CALLS = 4          # calls booked per day
TARGET_DOMAINS = 50       # domains scanned per day


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _clamp(value: float, lo: float = 0, hi: float = 100) -> int:
    return int(max(lo, min(hi, value)))


def run_weekly_va_scoring() -> dict:
    """Score every active VA for the most recent 7-day period."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}

    headers = _sb_headers()
    now = datetime.now(timezone.utc)
    # week_start = most recent Monday at 00:00 UTC
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = week_start
    period_start = week_start - timedelta(days=7)
    week_start_iso = period_start.strftime("%Y-%m-%d")

    # Fetch active VAs
    va_res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/va_profiles",
        headers=headers,
        params={"status": "eq.active", "select": "id", "limit": "200"},
        timeout=30.0,
    )
    va_res.raise_for_status()
    va_ids = [row["id"] for row in va_res.json() or []]
    if not va_ids:
        return {"ok": True, "scored": 0, "message": "no active VAs"}

    scored = 0
    for va_id in va_ids:
        # Fetch daily reports for the period
        dr_res = httpx.get(
            f"{SUPABASE_URL}/rest/v1/va_daily_reports",
            headers=headers,
            params={
                "va_id": f"eq.{va_id}",
                "report_date": f"gte.{period_start.strftime('%Y-%m-%d')}",
                "select": "emails_sent,replies_received,positive_replies,calls_booked,domains_scanned",
                "limit": "7",
            },
            timeout=20.0,
        )
        dr_res.raise_for_status()
        reports = dr_res.json() or []
        days = len(reports) or 1

        total_emails = sum(r.get("emails_sent", 0) for r in reports)
        total_replies = sum(r.get("replies_received", 0) for r in reports)
        total_positive = sum(r.get("positive_replies", 0) for r in reports)
        total_calls = sum(r.get("calls_booked", 0) for r in reports)
        total_domains = sum(r.get("domains_scanned", 0) for r in reports)

        # Normalise to 0-100 vs daily targets * days
        output_score = _clamp((total_emails / (TARGET_EMAILS * days)) * 100) if days else 0
        accuracy_score = _clamp((total_domains / (TARGET_DOMAINS * days)) * 100) if days else 0
        reply_quality_score = _clamp((total_positive / (TARGET_POSITIVE * days)) * 100) if days else 0
        booking_score = _clamp((total_calls / (TARGET_CALLS * days)) * 100) if days else 0

        total_score = _clamp(
            output_score * 0.30
            + accuracy_score * 0.25
            + reply_quality_score * 0.25
            + booking_score * 0.20
        )

        if total_score >= 80:
            standing = "green"
        elif total_score >= 60:
            standing = "yellow"
        else:
            standing = "red"

        # Upsert score
        upsert_res = httpx.post(
            f"{SUPABASE_URL}/rest/v1/va_scores",
            headers={**headers, "Prefer": "resolution=merge-duplicates,return=representation"},
            json={
                "va_id": va_id,
                "week_start": week_start_iso,
                "output_score": output_score,
                "accuracy_score": accuracy_score,
                "reply_quality_score": reply_quality_score,
                "booking_score": booking_score,
                "total_score": total_score,
                "standing": standing,
            },
            timeout=20.0,
        )
        if upsert_res.status_code < 400:
            scored += 1
        else:
            logger.warning("va score upsert failed va=%s: %s", va_id, upsert_res.text[:300])

    return {"ok": True, "scored": scored, "week_start": week_start_iso}
