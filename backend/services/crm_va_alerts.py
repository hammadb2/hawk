"""Daily VA alert checks — runs once per day.

Creates va_alerts rows when:
- Calls booked < 15 by 3pm local time (team total)
- Bounce rate > 3% on any domain
- Reply rate < 2% for 3 consecutive days (per VA)
- VA misses daily input submission by end of shift
- VA score drops to red
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _insert_alert(alert_type: str, message: str, va_id: str | None = None, domain: str | None = None) -> None:
    payload: dict = {
        "alert_type": alert_type,
        "message": message,
    }
    if va_id:
        payload["va_id"] = va_id
    if domain:
        payload["domain"] = domain
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/va_alerts",
            headers=_sb_headers(),
            json=payload,
            timeout=15.0,
        ).raise_for_status()
    except Exception as e:
        logger.warning("Failed to insert VA alert: %s", e)


def run_daily_va_alerts() -> dict:
    """Run all VA alert checks."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}

    headers = _sb_headers()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    alerts_created = 0

    # 1) Calls booked < 15 by 3pm (check runs at end of day, use today's reports)
    dr_res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/va_daily_reports",
        headers=headers,
        params={
            "report_date": f"eq.{today}",
            "select": "va_id,calls_booked",
            "limit": "200",
        },
        timeout=30.0,
    )
    dr_res.raise_for_status()
    today_reports = dr_res.json() or []
    total_calls = sum(r.get("calls_booked", 0) for r in today_reports)
    if total_calls < 15 and today_reports:
        _insert_alert("low_calls", f"Team calls booked today: {total_calls} (target: 15+)")
        alerts_created += 1

    # 2) Bounce rate > 3% on any domain
    dh_res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/domain_health",
        headers=headers,
        params={"bounce_rate": "gt.3", "status": "neq.paused", "select": "id,domain,bounce_rate", "limit": "50"},
        timeout=20.0,
    )
    dh_res.raise_for_status()
    for d in dh_res.json() or []:
        _insert_alert(
            "high_bounce",
            f"Domain {d['domain']} bounce rate at {d['bounce_rate']:.1f}%",
            domain=d["domain"],
        )
        alerts_created += 1

    # 3) Reply rate < 2% for 3 consecutive days (per VA)
    va_res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/va_profiles",
        headers=headers,
        params={"status": "eq.active", "select": "id,full_name", "limit": "200"},
        timeout=20.0,
    )
    va_res.raise_for_status()
    active_vas = va_res.json() or []
    three_days_ago = (now - timedelta(days=3)).strftime("%Y-%m-%d")

    for va in active_vas:
        va_id = va["id"]
        va_name = va.get("full_name", va_id[:8])

        # Recent 3-day reports
        rr_res = httpx.get(
            f"{SUPABASE_URL}/rest/v1/va_daily_reports",
            headers=headers,
            params={
                "va_id": f"eq.{va_id}",
                "report_date": f"gte.{three_days_ago}",
                "select": "emails_sent,replies_received",
                "order": "report_date.desc",
                "limit": "3",
            },
            timeout=15.0,
        )
        rr_res.raise_for_status()
        recent = rr_res.json() or []
        if len(recent) >= 3:
            all_low = True
            for r in recent:
                sent = r.get("emails_sent", 0)
                replies = r.get("replies_received", 0)
                rate = (replies / sent * 100) if sent > 0 else 0
                if rate >= 2:
                    all_low = False
                    break
            if all_low:
                _insert_alert("low_reply_rate", f"{va_name}: reply rate < 2% for 3 consecutive days", va_id=va_id)
                alerts_created += 1

    # 4) Missed daily input — active VAs with no report for today
    reported_va_ids = {r.get("va_id") for r in today_reports}
    for va in active_vas:
        if va["id"] not in reported_va_ids:
            _insert_alert(
                "missed_input",
                f"{va.get('full_name', va['id'][:8])} has not submitted today's report",
                va_id=va["id"],
            )
            alerts_created += 1

    # 5) VA score dropped to red
    sc_res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/va_scores",
        headers=headers,
        params={
            "standing": "eq.red",
            "select": "va_id",
            "order": "week_start.desc",
            "limit": "200",
        },
        timeout=20.0,
    )
    sc_res.raise_for_status()
    red_va_ids = {r["va_id"] for r in sc_res.json() or []}
    for va in active_vas:
        if va["id"] in red_va_ids:
            _insert_alert("red_score", f"{va.get('full_name', va['id'][:8])} has a RED standing", va_id=va["id"])
            alerts_created += 1

    return {"ok": True, "alerts_created": alerts_created}
