"""Cron: escalate unhandled ARIA replies past 30 minutes (CEO WhatsApp once)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

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
        "Content-Type": "application/json",
    }


def run_va_reply_escalation() -> dict:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "Supabase not configured"}
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_headers(),
        params={
            "reply_received_at": "not.is.null",
            "va_actioned_at": "is.null",
            "va_escalation_sent_at": "is.null",
            "select": "id,company_name,domain,reply_received_at",
            "limit": "200",
        },
        timeout=30.0,
    )
    r.raise_for_status()
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=30)
    rows = []
    for row in r.json() or []:
        rt = row.get("reply_received_at")
        if not rt:
            continue
        try:
            rdt = datetime.fromisoformat(str(rt).replace("Z", "+00:00"))
            if rdt <= cutoff_dt:
                rows.append(row)
        except Exception:
            continue
    n = 0
    ceo = CRM_CEO_PHONE_E164 or "+18259458282"
    for row in rows:
        pid = row["id"]
        co = row.get("company_name") or row.get("domain") or "Prospect"
        try:
            send_sms(
                ceo,
                "Unhandled reply — "
                f"{co} — "
                "30 minutes with no action. "
                "Check ARIA replies dashboard.",
            )
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_headers(),
                params={"id": f"eq.{pid}"},
                json={"va_escalation_sent_at": datetime.now(timezone.utc).isoformat()},
                timeout=15.0,
            ).raise_for_status()
            n += 1
        except Exception as e:
            logger.exception("va escalation prospect=%s: %s", pid, e)
    return {"ok": True, "escalated": n}
