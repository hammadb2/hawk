"""Award portal gamification milestones (hawk_certified, thirty_days_clean)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        raw = str(raw).replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _findings_list(scan: dict[str, Any]) -> list[dict[str, Any]]:
    raw = scan.get("findings")
    if isinstance(raw, dict):
        fl = raw.get("findings")
        if isinstance(fl, list):
            return [x for x in fl if isinstance(x, dict)]
    return []


def _severity_rank(s: str) -> int:
    x = (s or "").lower()
    return {"critical": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 4}.get(x, 5)


def _scan_has_critical_or_high(scan: dict[str, Any]) -> bool:
    for f in _findings_list(scan):
        if _severity_rank(str(f.get("severity") or "")) <= 1:
            return True
    return False


def _milestone_exists(client_id: str, key: str) -> bool:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_security_milestones",
        headers=_sb(),
        params={
            "client_id": f"eq.{client_id}",
            "milestone_key": f"eq.{key}",
            "select": "id",
            "limit": "1",
        },
        timeout=15.0,
    )
    if r.status_code != 200:
        return False
    return bool(r.json())


def _insert_milestone(client_id: str, key: str, metadata: dict[str, Any]) -> None:
    mr = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_security_milestones",
        headers=_sb(),
        json={"client_id": client_id, "milestone_key": key, "metadata": metadata},
        timeout=15.0,
    )
    if mr.status_code >= 400 and mr.status_code != 409:
        logger.warning("milestone insert %s: %s", key, mr.text[:200])


def ensure_portal_milestones(client_id: str, prospect_id: str | None) -> None:
    """
    Insert hawk_certified / thirty_days_clean when criteria are met (idempotent via unique constraint).
    """
    if not SUPABASE_URL or not SERVICE_KEY or not client_id:
        return

    cl = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={"id": f"eq.{client_id}", "select": "certified_at", "limit": "1"},
        timeout=15.0,
    )
    if cl.status_code != 200:
        return
    crow = (cl.json() or [None])[0] or {}
    if crow.get("certified_at") and not _milestone_exists(client_id, "hawk_certified"):
        _insert_milestone(client_id, "hawk_certified", {"source": "certified_at"})

    if not prospect_id:
        return

    sc = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers=_sb(),
        params={
            "prospect_id": f"eq.{prospect_id}",
            "select": "id,created_at,findings",
            "order": "created_at.asc",
            "limit": "200",
        },
        timeout=30.0,
    )
    if sc.status_code != 200:
        return
    scans = sc.json() or []
    if len(scans) < 1:
        return

    now = datetime.now(timezone.utc)
    first_at = _parse_ts(scans[0].get("created_at"))
    if first_at:
        if first_at.tzinfo is None:
            first_at = first_at.replace(tzinfo=timezone.utc)
        if now - first_at < timedelta(days=30):
            return

    latest = scans[-1]
    if _scan_has_critical_or_high(latest):
        return

    if not _milestone_exists(client_id, "thirty_days_clean"):
        _insert_milestone(
            client_id,
            "thirty_days_clean",
            {"latest_scan_id": latest.get("id"), "rule": "30d_tenure_no_ch_on_latest"},
        )
