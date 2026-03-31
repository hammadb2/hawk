"""Process due client_onboarding_sequences rows (Phase 2B drip)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from config import CRM_PUBLIC_BASE_URL
from services.crm_portal_email import send_resend

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def process_due_onboarding_sequences() -> dict[str, Any]:
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "processed": 0, "reason": "no supabase"}

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_onboarding_sequences",
        headers=_headers(),
        params={
            "status": "eq.pending",
            "select": "id,client_id,step,metadata",
            "limit": "200",
        },
        timeout=60.0,
    )
    if r.status_code >= 400:
        logger.error("fetch sequences failed: %s", r.text[:300])
        return {"ok": False, "processed": 0}

    rows = r.json()
    now = datetime.now(timezone.utc)
    processed = 0

    for row in rows or []:
        meta = row.get("metadata") or {}
        sched = meta.get("scheduled_for")
        if not sched:
            continue
        try:
            dt = datetime.fromisoformat(str(sched).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt > now:
            continue

        sid = row["id"]
        step = row.get("step") or ""
        cid = row.get("client_id")
        if step == "welcome_email":
            continue

        cr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=_headers(),
            params={"id": f"eq.{cid}", "select": "company_name,domain", "limit": "1"},
            timeout=20.0,
        )
        cr.raise_for_status()
        clients = cr.json()
        company = (clients[0].get("company_name") or clients[0].get("domain") or "there") if clients else "there"
        cpp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
            headers=_headers(),
            params={"client_id": f"eq.{cid}", "select": "email", "limit": "1"},
            timeout=20.0,
        )
        cpp.raise_for_status()
        cprows = cpp.json()
        if not cprows:
            continue
        to_email = cprows[0].get("email")
        if not to_email:
            continue

        base = CRM_PUBLIC_BASE_URL
        portal = f"{base}/portal/login"
        subject = f"HAWK update — {step.replace('_', ' ').title()}"
        html = f"<p>Hi {company},</p><p>This is your scheduled onboarding step: <strong>{step}</strong>.</p><p><a href=\"{portal}\">Open portal</a></p>"

        try:
            send_resend(to_email=to_email, subject=subject, html=html)
        except Exception:
            logger.exception("resend failed step=%s", step)
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/client_onboarding_sequences",
                headers=_headers(),
                params={"id": f"eq.{sid}"},
                json={"status": "failed"},
                timeout=20.0,
            )
            continue

        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/client_onboarding_sequences",
            headers=_headers(),
            params={"id": f"eq.{sid}"},
            json={"status": "sent", "sent_at": now.isoformat()},
            timeout=20.0,
        )
        processed += 1

    return {"ok": True, "processed": processed}
