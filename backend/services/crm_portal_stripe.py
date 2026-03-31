"""Stripe checkout.session.completed → provision client portal user + onboarding sequence."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import CRM_PUBLIC_BASE_URL, SUPABASE_URL
from services.crm_portal_email import welcome_portal_email

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _find_client_row(headers: dict[str, str], session_obj: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve CRM client from Stripe session metadata or stripe_customer_id / email domain."""
    meta = session_obj.get("metadata") or {}
    cid = meta.get("crm_client_id") or meta.get("client_id")
    if cid:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=headers,
            params={"id": f"eq.{cid}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]

    cust = session_obj.get("customer")
    if isinstance(cust, dict):
        cust = cust.get("id")
    if cust:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=headers,
            params={"stripe_customer_id": f"eq.{cust}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]

    email = (session_obj.get("customer_email") or "").strip().lower()
    if not email and session_obj.get("customer_details"):
        email = (session_obj["customer_details"].get("email") or "").strip().lower()
    if email and "@" in email:
        domain = email.split("@", 1)[1].strip().lower()
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=headers,
            params={"domain": f"eq.{domain}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]

    return None


def _invite_portal_user(*, email: str, company_name: str, client_id: str) -> str | None:
    """Supabase Auth invite; returns new auth user id."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return None

    redir = f"{CRM_PUBLIC_BASE_URL}/portal" if CRM_PUBLIC_BASE_URL else None
    payload: dict[str, Any] = {
        "email": email.lower().strip(),
        "data": {
            "full_name": company_name,
            "portal_client_id": client_id,
        },
    }
    if redir:
        payload["options"] = {"email_redirect_to": redir}

    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/invite",
        headers=_sb_headers(),
        json=payload,
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("portal invite failed %s: %s — trying existing user lookup", r.status_code, r.text[:300])
        return _lookup_user_id_by_email(email)

    out = r.json()
    uid = out.get("id") if isinstance(out, dict) else None
    if uid:
        return str(uid)
    user = out.get("user") if isinstance(out, dict) else None
    if isinstance(user, dict) and user.get("id"):
        return str(user["id"])
    return None


def _lookup_user_id_by_email(email: str) -> str | None:
    """Find auth user id by email via GoTrue admin list (paginated scan)."""
    want = email.lower().strip()
    page = 1
    for _ in range(20):
        r = httpx.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=_sb_headers(),
            params={"page": str(page), "per_page": "100"},
            timeout=30.0,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        users = data.get("users") if isinstance(data, dict) else []
        for u in users or []:
            if (u.get("email") or "").lower() == want:
                uid = u.get("id")
                return str(uid) if uid else None
        if not users or len(users) < 100:
            break
        page += 1
    return None


def _seed_onboarding_sequence(headers: dict[str, str], client_id: str, now: datetime) -> None:
    steps = [
        ("welcome_email", now),
        ("scan_results_email", now + timedelta(minutes=2)),
        ("top_finding_24h", now + timedelta(hours=24)),
        ("portal_reminder_72h", now + timedelta(hours=72)),
        ("weekly_digest_7d", now + timedelta(days=7)),
    ]
    for step, when in steps:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_onboarding_sequences",
            headers=headers,
            json={
                "client_id": client_id,
                "step": step,
                "status": "pending",
                "metadata": {"scheduled_for": when.isoformat()},
            },
            timeout=20.0,
        )
        if r.status_code >= 400:
            logger.warning("sequence seed step %s failed: %s", step, r.text[:200])


def provision_portal_from_checkout(event: dict[str, Any]) -> bool:
    """
    On checkout.session.completed, link Stripe payment to a CRM client and invite portal user.
    Returns True if provisioning ran (even if partially skipped).
    """
    if event.get("type") != "checkout.session.completed":
        return False
    if not SUPABASE_URL or not SERVICE_KEY:
        return False

    session_obj = (event.get("data") or {}).get("object") or {}
    if not isinstance(session_obj, dict):
        return False

    headers = _sb_headers()
    client_row = _find_client_row(headers, session_obj)
    if not client_row:
        logger.info("portal provision: no matching CRM client for checkout session")
        return False

    cid = str(client_row["id"])
    if client_row.get("portal_user_id"):
        logger.info("portal provision: client %s already has portal_user_id", cid)
        return True

    email = (session_obj.get("customer_email") or "").strip().lower()
    if not email and session_obj.get("customer_details"):
        email = (session_obj["customer_details"].get("email") or "").strip().lower()
    if not email:
        logger.warning("portal provision: no customer email on session")
        return False

    company = (client_row.get("company_name") or client_row.get("domain") or "there")[:200]
    uid = _invite_portal_user(email=email, company_name=str(company), client_id=cid)
    if not uid:
        logger.error("portal provision: could not create or resolve auth user for %s", email)
        return False

    patch = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=headers,
        params={"id": f"eq.{cid}"},
        json={
            "portal_user_id": uid,
            "onboarding_sequence_status": "in_progress",
        },
        timeout=20.0,
    )
    patch.raise_for_status()

    cpp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=headers,
        json={
            "user_id": uid,
            "client_id": cid,
            "email": email,
            "company_name": client_row.get("company_name"),
            "domain": client_row.get("domain"),
        },
        timeout=20.0,
    )
    if cpp.status_code >= 400:
        logger.error("client_portal_profiles insert failed: %s", cpp.text[:400])
        return False

    now = datetime.now(timezone.utc)
    _seed_onboarding_sequence(headers, cid, now)

    base = CRM_PUBLIC_BASE_URL
    portal_url = f"{base}/portal/login"
    try:
        welcome_portal_email(to_email=email, company_name=str(company), portal_url=portal_url)
    except Exception:
        logger.exception("welcome email failed")

    # Mark welcome step sent (best-effort)
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/client_onboarding_sequences",
        headers=headers,
        params={"client_id": f"eq.{cid}", "step": "eq.welcome_email"},
        json={"status": "sent", "sent_at": now.isoformat()},
        timeout=20.0,
    )

    return True
