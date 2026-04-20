"""Read boolean flags from public.crm_settings via Supabase REST (service role)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def parse_crm_bool(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in ("", "null"):
        return default
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    return default


def fetch_crm_bool(key: str, *, default: bool = True) -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return default
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}", "select": "value", "limit": "1"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json() or []
        if not rows:
            return default
        return parse_crm_bool(rows[0].get("value"), default)
    except Exception as exc:
        logger.warning("crm_settings %s bool lookup failed: %s", key, exc)
        return default
