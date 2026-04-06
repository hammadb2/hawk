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
    return frozenset({"ceo", "hos", "team_lead", "sales_rep", "closer"})


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
    body: dict[str, Any] = {"role": "client", "status": "active", "email": email, "full_name": company[:120]}
    if not rows:
        ins = httpx.post(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_headers(),
            json={"id": uid, **body},
            timeout=20.0,
        )
        if ins.status_code >= 400:
            logger.error("profiles insert failed: %s", ins.text[:400])
            ins.raise_for_status()
    else:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_headers(),
            params={"id": f"eq.{uid}"},
            json=body,
            timeout=20.0,
        ).raise_for_status()
