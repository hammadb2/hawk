"""Tiny read-through helper over ``crm_settings`` so service code doesn't
duplicate Supabase REST boilerplate. Single-process cache for 30 seconds —
cheap enough not to matter, keeps the auto-reply hot path out of the DB on
every inbound webhook.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import httpx

from config import SUPABASE_URL

logger = logging.getLogger(__name__)

_TTL_SECONDS = 30.0
_cache: dict[str, tuple[float, str]] = {}
_lock = threading.Lock()


def _sb_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def get_setting(key: str, default: str = "") -> str:
    """Return ``crm_settings.value`` for ``key`` or ``default`` on miss."""
    now = time.time()
    with _lock:
        cached = _cache.get(key)
        if cached and (now - cached[0]) < _TTL_SECONDS:
            return cached[1]
    if not SUPABASE_URL:
        return default
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}", "select": "value", "limit": "1"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json()
        value = str(rows[0].get("value", "")).strip() if rows else default
    except Exception as exc:
        logger.debug("get_setting(%s) failed: %s", key, exc)
        value = default
    with _lock:
        _cache[key] = (now, value)
    return value


def get_bool(key: str, default: bool = False) -> bool:
    value = get_setting(key, "").strip().lower()
    if not value:
        return default
    return value in ("true", "1", "yes", "y", "on")


def get_int(key: str, default: int) -> int:
    value = get_setting(key, "").strip()
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def invalidate(key: str | None = None) -> None:
    with _lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


def set_setting(key: str, value: Any) -> None:
    """Upsert ``crm_settings`` row via service-role. Invalidates cache on success."""
    if not SUPABASE_URL:
        return
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers={
                **_sb_headers(),
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            json={"key": key, "value": str(value)},
            timeout=10.0,
        ).raise_for_status()
        invalidate(key)
    except Exception:
        logger.exception("set_setting(%s) failed", key)


__all__ = ["get_setting", "get_bool", "get_int", "set_setting", "invalidate"]
