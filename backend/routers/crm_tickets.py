"""
CRM Tickets Router
Ticket stats endpoint requires service-role aggregation.
Simple CRUD (submit, list, update status) goes through Supabase JS client directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from backend.services.supabase_crm import supabase_available, get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/tickets", tags=["crm-tickets"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/stats")
async def ticket_stats():
    """
    Ticket statistics for the self-healing console.
    Returns open/in-progress counts, resolved today, critical open, avg resolution time.
    """
    if not supabase_available():
        return _empty_stats()

    try:
        sb = get_supabase()

        open_res = (
            sb.table("tickets")
            .select("id", count="exact")
            .eq("status", "open")
            .execute()
        )
        in_progress_res = (
            sb.table("tickets")
            .select("id", count="exact")
            .eq("status", "in_progress")
            .execute()
        )
        critical_res = (
            sb.table("tickets")
            .select("id", count="exact")
            .in_("status", ["open", "in_progress"])
            .eq("severity", "critical")
            .execute()
        )

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        resolved_today_res = (
            sb.table("tickets")
            .select("id", count="exact")
            .in_("status", ["resolved", "closed"])
            .gte("resolved_at", today)
            .execute()
        )

        # Average resolution time (hours) for tickets resolved in the last 30 days
        thirty_days_ago = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from datetime import timedelta
        thirty_days_ago = (thirty_days_ago - timedelta(days=30)).isoformat()

        resolved_res = (
            sb.table("tickets")
            .select("created_at, resolved_at")
            .in_("status", ["resolved", "closed"])
            .gte("resolved_at", thirty_days_ago)
            .not_.is_("resolved_at", "null")
            .execute()
        )

        avg_hours = 0.0
        resolution_times = []
        for ticket in (resolved_res.data or []):
            try:
                created = datetime.fromisoformat(ticket["created_at"].replace("Z", "+00:00"))
                resolved = datetime.fromisoformat(ticket["resolved_at"].replace("Z", "+00:00"))
                hours = (resolved - created).total_seconds() / 3600
                resolution_times.append(hours)
            except (ValueError, TypeError, KeyError):
                pass

        if resolution_times:
            avg_hours = round(sum(resolution_times) / len(resolution_times), 1)

        return {
            "open": open_res.count or 0,
            "in_progress": in_progress_res.count or 0,
            "resolved_today": resolved_today_res.count or 0,
            "critical_open": critical_res.count or 0,
            "avg_resolution_hours": avg_hours,
        }

    except Exception as exc:
        logger.error("ticket_stats error: %s", exc)
        return _empty_stats()


def _empty_stats() -> dict:
    return {
        "open": 0,
        "in_progress": 0,
        "resolved_today": 0,
        "critical_open": 0,
        "avg_resolution_hours": 0.0,
    }
