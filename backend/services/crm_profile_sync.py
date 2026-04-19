"""Shared Supabase profiles updates for client portal users (avoid circular imports)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from config import SUPABASE_URL

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def profile_role(uid: str) -> str | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"id": f"eq.{uid}", "select": "role", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    return (rows[0].get("role") or "").lower() or None


def staff_roles() -> frozenset[str]:
    """CRM seats that are not client portal users (includes VA seats when stored as sales_rep/closer)."""
    return frozenset({"ceo", "hos", "team_lead", "sales_rep", "closer", "va", "va_manager"})


PORTAL_TEAM_EMAIL_MESSAGE = (
    "This email is already a team member account and cannot be used for a client portal."
)


def portal_uid_blocks_client_portal(uid: str) -> bool:
    """
    True if this auth user already has a non-client profiles row (CRM team / invited rep / VA, any status).
    Used to block client portal provisioning for team accounts.
    """
    if not SUPABASE_URL or not SERVICE_KEY or not uid:
        return False
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"id": f"eq.{uid}", "select": "role,role_type", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return False
    row = rows[0]
    role = (row.get("role") or "").lower()
    if role == "client":
        return False
    rt = (row.get("role_type") or "").lower()
    if rt in ("va_outreach", "va_manager"):
        return True
    return bool(role and role != "client")


def portal_email_blocks_client_portal(email: str) -> bool:
    """
    True if any profiles row uses this email with a non-client CRM seat.
    Same email cannot be both team and client portal per product rules.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return False
    em = email.strip().lower()
    if "@" not in em:
        return False
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"email": f"eq.{em}", "select": "id,role,role_type"},
        timeout=20.0,
    )
    r.raise_for_status()
    for row in r.json() or []:
        role = (row.get("role") or "").lower()
        if role == "client":
            continue
        rt = (row.get("role_type") or "").lower()
        if rt in ("va_outreach", "va_manager"):
            return True
        if role and role != "client":
            return True
    return False


def ensure_client_profile(uid: str, email: str, company: str) -> None:
    """Insert or patch profiles row: role=client for portal access."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"id": f"eq.{uid}", "select": "id,role", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    base: dict[str, Any] = {
        "role": "client",
        "status": "active",
        "email": email,
        "full_name": company[:120],
    }
    with_rt: dict[str, Any] = {**base, "role_type": "client"}

    if not rows:
        ins = httpx.post(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_headers(),
            json={"id": uid, **with_rt},
            timeout=20.0,
        )
        if ins.status_code >= 400:
            ins2 = httpx.post(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=_headers(),
                json={"id": uid, **base},
                timeout=20.0,
            )
            if ins2.status_code >= 400:
                logger.error("profiles insert failed: %s", ins2.text[:400])
                ins2.raise_for_status()
    else:
        pr = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_headers(),
            params={"id": f"eq.{uid}"},
            json=with_rt,
            timeout=20.0,
        )
        if pr.status_code >= 400:
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=_headers(),
                params={"id": f"eq.{uid}"},
                json=base,
                timeout=20.0,
            ).raise_for_status()
