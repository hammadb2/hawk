"""Optional Redis + Supabase mirror for fast scan results (24h TTL per domain)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
_SB_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
CACHE_TTL_SEC = 86400


def _redis():
    if not REDIS_URL:
        return None
    try:
        import redis

        return redis.Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning("Redis unavailable for scan cache: %s", e)
        return None


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": _SB_KEY,
        "Authorization": f"Bearer {_SB_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def cache_key(domain: str, depth: str) -> str:
    d = domain.strip().lower()
    return f"hawk:scan:{depth}:{d}"


def get_cached_scan(domain: str, depth: str = "fast") -> dict[str, Any] | None:
    r = _redis()
    key = cache_key(domain, depth)
    if r:
        try:
            raw = r.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("redis get scan cache: %s", e)
    if not SUPABASE_URL or not _SB_KEY:
        return None
    try:
        res = httpx.get(
            f"{SUPABASE_URL}/rest/v1/scanner_cache",
            headers=_sb_headers(),
            params={
                "domain": f"eq.{domain.strip().lower()}",
                "scan_depth": f"eq.{depth}",
                "select": "result,expires_at",
                "limit": "1",
            },
            timeout=12.0,
        )
        res.raise_for_status()
        rows = res.json()
        if not rows:
            return None
        exp = rows[0].get("expires_at")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                if exp_dt < datetime.now(timezone.utc):
                    return None
            except Exception:
                pass
        data = rows[0].get("result")
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("supabase scan cache read: %s", e)
        return None


def set_cached_scan(domain: str, depth: str, result: dict[str, Any]) -> None:
    if result.get("message") == "scan_timeout" or result.get("score") is None:
        return
    key = cache_key(domain, depth)
    r = _redis()
    if r:
        try:
            r.setex(key, CACHE_TTL_SEC, json.dumps(result))
        except Exception as e:
            logger.warning("redis set scan cache: %s", e)
    if not SUPABASE_URL or not _SB_KEY:
        return
    try:
        exp = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        row = {
            "domain": domain.strip().lower(),
            "scan_depth": depth,
            "result": result,
            "expires_at": exp,
        }
        # Atomic upsert: on conflict (domain, scan_depth) merge into existing row
        upsert_headers = {**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=representation"}
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/scanner_cache",
            headers=upsert_headers,
            json=row,
            timeout=12.0,
        ).raise_for_status()
    except Exception as e:
        logger.warning("supabase scan cache write: %s", e)
