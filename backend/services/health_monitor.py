"""Self-healing integration monitor — logs to system_health_log, WhatsApp on consecutive failures."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from config import CRM_CEO_PHONE_E164, MONITOR_API_BASE_URL, SMARTLEAD_API_KEY, STRIPE_SECRET_KEY, SUPABASE_URL
from services.crm_openphone import send_sms

logger = logging.getLogger(__name__)

SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
PORT = os.environ.get("PORT", "8000").strip() or "8000"

# ARIA outbound pipeline: alert if no events for this long during business hours (MST)
EMAIL_FRESH_WARN_HOURS = int(os.environ.get("MONITOR_EMAIL_FRESH_WARN_HOURS", "2"))
EMAIL_FRESH_FAIL_HOURS = int(os.environ.get("MONITOR_EMAIL_FRESH_FAIL_HOURS", "48"))


def _sb_headers_read() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


def _sb_headers_write() -> dict[str, str]:
    return {
        **_sb_headers_read(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _insert_log(
    *,
    service: str,
    status: str,
    response_ms: int,
    detail: dict[str, Any],
    alert_sent: bool = False,
) -> dict[str, Any] | None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("Supabase not configured — skip health log insert")
        return None
    body = {
        "service": service,
        "status": status,
        "response_ms": response_ms,
        "detail": detail,
        "alert_sent": alert_sent,
    }
    try:
        r = httpx.post(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/system_health_log",
            headers=_sb_headers_write(),
            json=body,
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else None
    except Exception as e:
        logger.exception("system_health_log insert failed: %s", e)
        return None


def _fetch_previous_log(service: str) -> dict[str, Any] | None:
    try:
        r = httpx.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/system_health_log",
            headers=_sb_headers_read(),
            params={
                "service": f"eq.{service}",
                "select": "id,status,alert_sent,checked_at",
                "order": "checked_at.desc",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception as e:
        logger.exception("fetch previous health log: %s", e)
        return None


def _patch_alert_sent(log_id: str, alert_sent: bool = True) -> None:
    try:
        httpx.patch(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/system_health_log",
            headers=_sb_headers_write(),
            params={"id": f"eq.{log_id}"},
            json={"alert_sent": alert_sent},
            timeout=15.0,
        )
    except Exception as e:
        logger.exception("patch alert_sent: %s", e)


def _maybe_ceo_sms(*, service: str, status: str, prev: dict[str, Any] | None, new_row: dict[str, Any] | None) -> None:
    ceo = CRM_CEO_PHONE_E164 or "+18259458282"
    if not new_row:
        return
    nid = new_row.get("id")
    if not nid:
        return

    if status == "failed" and prev and prev.get("status") == "failed" and not prev.get("alert_sent"):
        msg = f"HAWK monitor: {service} failed twice in a row. Check system_health_log in CRM Settings."
        send_sms(ceo, msg)
        _patch_alert_sent(str(nid), True)
        return

    if status == "ok" and prev and prev.get("status") == "failed" and prev.get("alert_sent"):
        msg = f"HAWK monitor: {service} recovered after failure."
        send_sms(ceo, msg)


def _timed_request(method: str, url: str, **kwargs: Any) -> tuple[str, int, dict[str, Any]]:
    t0 = time.perf_counter()
    try:
        r = httpx.request(method, url, timeout=kwargs.pop("timeout", 20.0), **kwargs)
        ms = int((time.perf_counter() - t0) * 1000)
        ok = 200 <= r.status_code < 300
        detail: dict[str, Any] = {"http_status": r.status_code}
        if not ok:
            detail["body_preview"] = (r.text or "")[:300]
        status = "ok" if ok else "failed"
        return status, ms, detail
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return "failed", ms, {"error": str(e)[:500]}


def _mst_business_hours() -> bool:
    now = datetime.now(ZoneInfo("America/Denver"))
    if now.weekday() >= 5:
        return False
    h = now.hour
    return 9 <= h < 17


def check_api() -> tuple[str, int, dict[str, Any]]:
    base = (MONITOR_API_BASE_URL or "").strip() or f"http://127.0.0.1:{PORT}"
    url = base if base.endswith("/health") else f"{base}/health"
    return _timed_request("GET", url)


def check_supabase_rest() -> tuple[str, int, dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return "failed", 0, {"error": "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing"}
    return _timed_request(
        "GET",
        f"{SUPABASE_URL.rstrip('/')}/rest/v1/profiles",
        headers=_sb_headers_read(),
        params={"select": "id", "limit": "1"},
    )


def check_smartlead() -> tuple[str, int, dict[str, Any]]:
    if not SMARTLEAD_API_KEY:
        return "degraded", 0, {"reason": "SMARTLEAD_API_KEY not set"}
    url = f"https://server.smartlead.ai/api/v1/campaigns?api_key={SMARTLEAD_API_KEY}"
    st, ms, d = _timed_request("GET", url)
    if st == "failed" and d.get("http_status") in (401, 403):
        return "degraded", ms, d
    return st, ms, d


def check_stripe() -> tuple[str, int, dict[str, Any]]:
    if not STRIPE_SECRET_KEY:
        return "degraded", 0, {"reason": "STRIPE_SECRET_KEY not set"}
    t0 = time.perf_counter()
    try:
        import stripe

        stripe.api_key = STRIPE_SECRET_KEY
        stripe.Balance.retrieve()
        ms = int((time.perf_counter() - t0) * 1000)
        return "ok", ms, {"livemode": True}
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return "failed", ms, {"error": str(e)[:400]}


def check_aria_email_freshness() -> tuple[str, int, dict[str, Any]]:
    """Last prospect_email_events row age — stale pipeline during business hours is degraded."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return "failed", 0, {"error": "supabase not configured"}
    t0 = time.perf_counter()
    try:
        r = httpx.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/prospect_email_events",
            headers=_sb_headers_read(),
            params={"select": "created_at", "order": "created_at.desc", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json() or []
        ms = int((time.perf_counter() - t0) * 1000)
        if not rows:
            return "degraded", ms, {"reason": "no prospect_email_events rows yet"}
        raw = rows[0].get("created_at")
        if not raw:
            return "degraded", ms, {"reason": "missing created_at"}
        last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - last.astimezone(timezone.utc)
        hours = age.total_seconds() / 3600.0
        detail = {"last_event_hours": round(hours, 2), "last_event_at": raw}
        if hours >= EMAIL_FRESH_FAIL_HOURS:
            return "failed", ms, detail
        if hours >= EMAIL_FRESH_WARN_HOURS and _mst_business_hours():
            return "degraded", ms, detail
        return "ok", ms, detail
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return "failed", ms, {"error": str(e)[:400]}


def run_health_monitor() -> dict[str, Any]:
    """Run all checks, insert logs, optionally WhatsApp CEO."""
    checks: list[tuple[str, Any]] = [
        ("api", check_api),
        ("supabase", check_supabase_rest),
        ("smartlead", check_smartlead),
        ("stripe", check_stripe),
        ("aria_email", check_aria_email_freshness),
    ]
    results: list[dict[str, Any]] = []
    for name, fn in checks:
        prev = _fetch_previous_log(name)
        status, ms, detail = fn()
        row = _insert_log(service=name, status=status, response_ms=ms, detail=detail)
        _maybe_ceo_sms(service=name, status=status, prev=prev, new_row=row)
        results.append({"service": name, "status": status, "response_ms": ms, "detail": detail})
    return {"ok": True, "checked_at": datetime.now(timezone.utc).isoformat(), "results": results}
