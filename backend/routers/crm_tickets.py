"""
CRM Tickets Router
Ticket stats use the real CRM schema (received / in_progress / resolved / duplicate / monitoring).
Simple CRUD (submit, list, update status) goes through Supabase JS client directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from backend.services.supabase_crm import supabase_available, get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/tickets", tags=["crm-tickets"])

OPEN_STATUSES = frozenset({"received", "in_progress", "monitoring"})
CLOSED_STATUSES = frozenset({"resolved", "duplicate"})


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@router.get("/stats")
async def ticket_stats():
    """
    Ticket statistics for the self-healing console (matches CRM `tickets` table + Next.js console).
    """
    if not supabase_available():
        return _empty_stats()

    try:
        sb = get_supabase()
        res = (
            sb.table("tickets")
            .select("id, status, severity, created_at, resolved_at, resolution_type, classification")
            .execute()
        )
        rows = res.data or []

        now = datetime.now(timezone.utc)
        four_hours_ago = now - timedelta(hours=4)

        open_over_4h = 0
        for r in rows:
            st = r.get("status") or ""
            if st not in OPEN_STATUSES:
                continue
            created = _parse_ts(r.get("created_at"))
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created and created < four_hours_ago:
                open_over_4h += 1

        resolution_hours: list[float] = []
        auto_count = 0
        user_error_count = 0
        resolved_total = 0

        for r in rows:
            st = r.get("status") or ""
            if st not in CLOSED_STATUSES:
                continue
            if not r.get("resolved_at"):
                continue
            resolved_total += 1

            rt = (r.get("resolution_type") or "").lower()
            cls = (r.get("classification") or "").lower()
            if "auto" in rt or "auto" in cls:
                auto_count += 1
            if "user" in rt and "error" in rt:
                user_error_count += 1
            elif "user_error" in cls or ("user" in cls and "error" in cls):
                user_error_count += 1

            created = _parse_ts(r.get("created_at"))
            resolved = _parse_ts(r.get("resolved_at"))
            if created and resolved:
                resolution_hours.append((resolved - created).total_seconds() / 3600.0)

        avg_hours = (
            round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else 0.0
        )
        auto_resolve_pct = round(100.0 * auto_count / resolved_total, 1) if resolved_total else 0.0
        user_error_pct = round(100.0 * user_error_count / resolved_total, 1) if resolved_total else 0.0

        return {
            "avg_resolution_hours": avg_hours,
            "auto_resolve_pct": auto_resolve_pct,
            "user_error_pct": user_error_pct,
            "open_over_4h": open_over_4h,
        }

    except Exception as exc:
        logger.error("ticket_stats error: %s", exc)
        return _empty_stats()


def _empty_stats() -> dict:
    return {
        "avg_resolution_hours": 0.0,
        "auto_resolve_pct": 0.0,
        "user_error_pct": 0.0,
        "open_over_4h": 0,
    }
