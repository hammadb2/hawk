"""ARIA Rolling Dispatcher — sends up to 200 emails/day per campaign (600/day total).

Runs every hour 9am-4pm MST (8 ticks), each tick dispatches the per-vertical
catch-up quota so the 600/day target is spread across business hours rather
than blasted at 6:30am. Primary source is `prospects` rows where
`pipeline_status=ready` (set by `aria_post_scan_pipeline`), ordered by
`hawk_score desc` so higher-signal leads go out first.

Design notes:
- Quota is computed by COUNTING prospects with `dispatched_at >= today` per
  vertical, so no separate counter table is needed and the count can't drift.
- Each tick: remaining = DAILY_CAP - sent_today; per_tick = remaining /
  remaining_ticks (ceil). Clamped to DAILY_CAP to avoid over-sends if a tick
  is skipped.
- Smartlead bulk upload reuses the helpers in `aria_morning_dispatch`.
- DB-level stage guard on the final PATCH (same pattern as post-scan + SLA)
  prevents regressing a prospect that a rep already advanced.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from config import SMARTLEAD_API_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

MST = ZoneInfo("America/Edmonton")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Per-vertical daily cap and the canonical tick schedule (9am–4pm MST inclusive = 8 ticks).
# Keep in sync with backend/main.py scheduler registration.
DAILY_CAP_PER_VERTICAL = int(os.environ.get("ARIA_DAILY_CAP_PER_VERTICAL", "200"))
DISPATCH_TICK_HOURS = [9, 10, 11, 12, 13, 14, 15, 16]
VERTICALS = ("dental", "legal", "accounting")


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _today_start_utc_iso() -> str:
    """Start-of-day in MST, rendered as UTC ISO for Supabase timestamptz filters."""
    now_mst = datetime.now(MST)
    start_mst = now_mst.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_mst.astimezone(timezone.utc).isoformat()


def _remaining_ticks_today() -> int:
    """How many more dispatch ticks (inclusive of current one) are left today."""
    current_hour = datetime.now(MST).hour
    remaining = [h for h in DISPATCH_TICK_HOURS if h >= current_hour]
    return max(1, len(remaining))


def _count_sent_today(vertical: str) -> int:
    if not SUPABASE_URL:
        return 0
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers={**_sb_headers(), "Prefer": "count=exact"},
            params={
                "select": "id",
                "industry": f"eq.{vertical}",
                "dispatched_at": f"gte.{_today_start_utc_iso()}",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        cr = r.headers.get("content-range", "")
        if "/" in cr:
            return int(cr.split("/", 1)[1])
    except Exception as exc:
        logger.warning("rolling-dispatch count sent_today vertical=%s failed: %s", vertical, exc)
    return 0


def _fetch_ready_prospects(vertical: str, limit: int) -> list[dict[str, Any]]:
    if not SUPABASE_URL or limit <= 0:
        return []
    params = {
        "select": (
            "id,domain,company_name,contact_email,contact_name,contact_title,"
            "email_subject,email_body,smartlead_campaign_id,hawk_score,"
            "vulnerability_found,city,province,industry,stage,pipeline_status"
        ),
        "pipeline_status": "eq.ready",
        "industry": f"eq.{vertical}",
        "stage": "in.(new,scanning,scanned)",
        "contact_email": "not.is.null",
        "email_subject": "not.is.null",
        "email_body": "not.is.null",
        "smartlead_campaign_id": "not.is.null",
        "order": "hawk_score.desc.nullslast,last_activity_at.asc",
        "limit": str(limit),
    }
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params=params,
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        logger.warning("rolling-dispatch fetch vertical=%s failed: %s", vertical, exc)
        return []


def _to_morning_dispatch_lead(prospect: dict[str, Any]) -> dict[str, Any]:
    """Adapt a prospect row to the dict shape `_bulk_upload_to_smartlead` expects."""
    return {
        "id": prospect["id"],
        "contact_email": prospect.get("contact_email", ""),
        "contact_name": prospect.get("contact_name") or "",
        "business_name": prospect.get("company_name") or "",
        "domain": prospect.get("domain") or "",
        "vertical": prospect.get("industry") or "",
        "city": prospect.get("city") or "",
        "province": prospect.get("province") or "",
        "hawk_score": prospect.get("hawk_score"),
        "vulnerability_found": prospect.get("vulnerability_found") or "",
        "email_subject": prospect.get("email_subject") or "",
        "email_body": prospect.get("email_body") or "",
    }


def _mark_prospects_dispatched(prospect_ids: list[str], campaign_id: str) -> int:
    """Flip prospects to stage=sent_email + pipeline_status=dispatched with stage guard."""
    if not prospect_ids or not SUPABASE_URL:
        return 0
    now_iso = datetime.now(timezone.utc).isoformat()
    patch = {
        "stage": "sent_email",
        "pipeline_status": "dispatched",
        "dispatched_at": now_iso,
        "smartlead_campaign_id": campaign_id or None,
        "last_activity_at": now_iso,
    }
    updated = 0
    # Chunk to keep PostgREST `in.()` predicates reasonable.
    for i in range(0, len(prospect_ids), 50):
        chunk = prospect_ids[i : i + 50]
        try:
            r = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
                params={
                    "id": f"in.({','.join(chunk)})",
                    "stage": "in.(new,scanning,scanned)",
                    "pipeline_status": "eq.ready",
                },
                json=patch,
                timeout=20.0,
            )
            r.raise_for_status()
            try:
                updated += len(r.json() or [])
            except Exception:
                updated += len(chunk)
        except Exception as exc:
            logger.warning("rolling-dispatch mark-dispatched chunk failed: %s", exc)
    return updated


def _quota_for_tick(vertical: str) -> tuple[int, int, int]:
    """Returns (sent_today, remaining_today, quota_for_this_tick)."""
    sent = _count_sent_today(vertical)
    remaining = max(0, DAILY_CAP_PER_VERTICAL - sent)
    if remaining == 0:
        return sent, 0, 0
    ticks_left = _remaining_ticks_today()
    per_tick = math.ceil(remaining / ticks_left)
    return sent, remaining, min(per_tick, remaining)


def run_rolling_dispatch() -> dict[str, Any]:
    """Public entrypoint. Safe to invoke manually outside tick hours."""
    start = datetime.now(timezone.utc)
    stats: dict[str, Any] = {
        "ok": True,
        "dispatched_total": 0,
        "by_vertical": {},
        "duration_seconds": 0,
    }
    if not SUPABASE_URL or not SERVICE_KEY:
        return {**stats, "ok": False, "reason": "supabase not configured"}
    if not SMARTLEAD_API_KEY:
        return {**stats, "ok": False, "reason": "smartlead api key not configured"}

    # Respect the global kill switch that morning-dispatch already honors.
    from services.aria_morning_dispatch import (
        _bulk_upload_to_smartlead,
        _ensure_campaign_sequence,
        _get_setting,
    )

    enabled = _get_setting("pipeline_dispatch_enabled", "true")
    if enabled.lower() not in ("true", "1", "yes"):
        return {**stats, "ok": False, "skipped": True, "reason": "pipeline_dispatch_enabled is false"}

    for vertical in VERTICALS:
        sent_today, remaining_today, quota = _quota_for_tick(vertical)
        if quota <= 0:
            stats["by_vertical"][vertical] = {
                "sent_today": sent_today,
                "remaining_today": remaining_today,
                "quota": 0,
                "uploaded": 0,
            }
            continue

        prospects = _fetch_ready_prospects(vertical, quota)
        if not prospects:
            stats["by_vertical"][vertical] = {
                "sent_today": sent_today,
                "remaining_today": remaining_today,
                "quota": quota,
                "uploaded": 0,
                "reason": "no ready prospects",
            }
            continue

        # Split by campaign_id — each prospect already has its vertical's campaign
        # resolved in aria_post_scan_pipeline, but we still group defensively in
        # case settings changed mid-day and different prospects have different ids.
        by_campaign: dict[str, list[dict[str, Any]]] = {}
        for p in prospects:
            cid = str(p.get("smartlead_campaign_id") or "")
            if cid:
                by_campaign.setdefault(cid, []).append(p)

        v_uploaded_total = 0
        v_breakdown: list[dict[str, Any]] = []
        for campaign_id, group in by_campaign.items():
            leads = [_to_morning_dispatch_lead(p) for p in group]
            _ensure_campaign_sequence(campaign_id, leads)
            uploaded = _bulk_upload_to_smartlead(campaign_id, leads)
            uploaded_ids = [str(lead["id"]) for lead in uploaded if lead.get("id")]
            # Only flip the stage + counter for leads Smartlead actually accepted.
            marked = _mark_prospects_dispatched(uploaded_ids, campaign_id)
            v_uploaded_total += marked
            v_breakdown.append(
                {
                    "campaign_id": campaign_id,
                    "attempted": len(leads),
                    "uploaded": len(uploaded),
                    "marked": marked,
                }
            )

        stats["by_vertical"][vertical] = {
            "sent_today": sent_today,
            "remaining_today": remaining_today,
            "quota": quota,
            "uploaded": v_uploaded_total,
            "campaigns": v_breakdown,
        }
        stats["dispatched_total"] += v_uploaded_total

    stats["duration_seconds"] = int((datetime.now(timezone.utc) - start).total_seconds())
    logger.info("rolling-dispatch complete: %s", json.dumps(stats))
    return stats
