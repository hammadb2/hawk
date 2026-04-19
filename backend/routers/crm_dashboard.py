"""CRM dashboard KPI aggregation — small JSON, 60s in-memory cache per user."""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from config import SUPABASE_ANON_KEY, SUPABASE_URL
from routers.crm_auth import require_supabase_uid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm", tags=["crm-dashboard"])

_kpi_lock = threading.Lock()
_kpi_cache: dict[str, tuple[float, dict[str, Any], tuple[str, str]]] = {}
_KPI_TTL_SEC = 60.0

_OPEN_STAGES = ("new", "scanned", "loom_sent", "replied", "call_booked", "proposal_sent")


def _user_rest_headers(authorization: str) -> dict[str, str]:
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="SUPABASE_URL not configured")
    if not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_ANON_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY required for dashboard KPIs",
        )
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": authorization.strip(),
        "Content-Type": "application/json",
    }


def _parse_count_header(content_range: str | None) -> int:
    if not content_range:
        return 0
    m = re.search(r"/(\d+)$", content_range.strip())
    if not m:
        return 0
    return int(m.group(1))


def _estimate_pipeline_dollars(hawk_score: int) -> int:
    if hawk_score >= 70:
        return 5000
    if hawk_score >= 40:
        return 2500
    return 1000


def _default_day_month_iso() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    return day_start, month_start


def _compute_kpis(authorization: str, day_start: str, month_start: str) -> dict[str, Any]:
    headers = _user_rest_headers(authorization)
    base = f"{SUPABASE_URL}/rest/v1"
    stale_cut = (datetime.fromisoformat(day_start.replace("Z", "+00:00")) - timedelta(hours=48)).isoformat()

    out: dict[str, Any] = {
        "prospects_by_stage": {},
        "active_clients_count": 0,
        "mrr_total_cents": 0,
        "calls_booked_today": 0,
        "emails_sent_today": 0,
        "emails_replied_today": 0,
        "hot_leads_count": 0,
        "closes_mtd": 0,
        "pipeline_open_dollars": 0,
        "stale_48h_open": 0,
    }

    with httpx.Client(timeout=30.0) as client:
        # --- prospects: count per stage (aggregate) ---
        try:
            r = client.get(f"{base}/prospects", params={"select": "stage,count()"}, headers=headers)
            r.raise_for_status()
            rows = r.json()
            by_stage: dict[str, int] = {}
            for row in rows:
                st = str(row.get("stage") or "")
                raw_c = row.get("count")
                if raw_c is None:
                    raw_c = row.get("count_1")
                by_stage[st] = int(raw_c or 0)
            out["prospects_by_stage"] = by_stage
        except Exception as e:
            logger.warning("prospects stage aggregate failed: %s", e)

        # --- open prospects: pipeline $ + stale (minimal columns) ---
        try:
            in_list = ",".join(_OPEN_STAGES)
            r = client.get(
                f"{base}/prospects",
                params={
                    "select": "stage,hawk_score,last_activity_at",
                    "stage": f"in.({in_list})",
                },
                headers=headers,
            )
            r.raise_for_status()
            open_rows = r.json()
            pipe = 0
            stale = 0
            for row in open_rows:
                hs = int(row.get("hawk_score") or 0)
                pipe += _estimate_pipeline_dollars(hs)
                la = row.get("last_activity_at")
                if la and str(la) < stale_cut:
                    stale += 1
            out["pipeline_open_dollars"] = pipe
            out["stale_48h_open"] = stale
        except Exception as e:
            logger.warning("open prospects aggregate failed: %s", e)

        # --- active clients count + MRR sum ---
        try:
            r = client.get(
                f"{base}/clients",
                params={"status": "eq.active", "select": "id"},
                headers={**headers, "Prefer": "count=exact"},
            )
            r.raise_for_status()
            out["active_clients_count"] = _parse_count_header(r.headers.get("content-range"))
        except Exception as e:
            logger.warning("active clients count failed: %s", e)

        try:
            r = client.get(
                f"{base}/clients",
                params={"status": "eq.active", "select": "mrr_cents.sum()"},
                headers=headers,
            )
            r.raise_for_status()
            sums = r.json()
            if isinstance(sums, list) and sums:
                sv = sums[0].get("sum")
                out["mrr_total_cents"] = int(sv) if sv is not None else 0
        except Exception as e:
            logger.warning("mrr sum failed: %s", e)

        # --- hot leads ---
        try:
            r = client.get(
                f"{base}/prospects",
                params={"is_hot": "eq.true", "select": "id"},
                headers={**headers, "Prefer": "count=exact"},
            )
            r.raise_for_status()
            out["hot_leads_count"] = _parse_count_header(r.headers.get("content-range"))
        except Exception as e:
            logger.warning("hot leads count failed: %s", e)

        # --- email events today ---
        try:
            r = client.get(
                f"{base}/prospect_email_events",
                params={"created_at": f"gte.{day_start}", "select": "id"},
                headers={**headers, "Prefer": "count=exact"},
            )
            r.raise_for_status()
            out["emails_sent_today"] = _parse_count_header(r.headers.get("content-range"))
        except Exception as e:
            logger.warning("email events count failed: %s", e)

        try:
            r = client.get(
                f"{base}/prospect_email_events",
                params={"replied_at": f"gte.{day_start}", "select": "id"},
                headers={**headers, "Prefer": "count=exact"},
            )
            r.raise_for_status()
            out["emails_replied_today"] = _parse_count_header(r.headers.get("content-range"))
        except Exception as e:
            logger.warning("email replies count failed: %s", e)

        # --- activities: calls booked today (stage_changed → call_booked) ---
        try:
            r = client.get(
                f"{base}/activities",
                params={
                    "type": "eq.stage_changed",
                    "created_at": f"gte.{day_start}",
                    "select": "id,metadata,created_at",
                    "limit": "500",
                },
                headers=headers,
            )
            r.raise_for_status()
            acts = r.json()
            n = 0
            for a in acts:
                meta = a.get("metadata") or {}
                to = meta.get("to") if isinstance(meta, dict) else None
                if to == "call_booked" and str(a.get("created_at") or "") >= day_start:
                    n += 1
            out["calls_booked_today"] = n
        except Exception as e:
            logger.warning("activities calls booked failed: %s", e)

        # --- closes MTD ---
        try:
            r = client.get(
                f"{base}/clients",
                params={"close_date": f"gte.{month_start}", "select": "id"},
                headers={**headers, "Prefer": "count=exact"},
            )
            r.raise_for_status()
            out["closes_mtd"] = _parse_count_header(r.headers.get("content-range"))
        except Exception as e:
            logger.warning("closes mtd count failed: %s", e)

    return out


def _crm_uid_and_auth(authorization: str | None = Header(default=None)) -> tuple[str, str]:
    uid = require_supabase_uid(authorization)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return uid, authorization


@router.get("/dashboard/kpis")
def get_dashboard_kpis(
    auth: tuple[str, str] = Depends(_crm_uid_and_auth),
    day_start: str | None = None,
    month_start: str | None = None,
) -> dict[str, Any]:
    """Aggregated CRM KPIs for the CEO live dashboard (RLS-scoped via caller JWT)."""
    uid, authorization = auth
    d_day, d_month = _default_day_month_iso()
    day = day_start or d_day
    month = month_start or d_month

    now = time.time()
    with _kpi_lock:
        hit = _kpi_cache.get(uid)
        if hit and hit[0] > now and hit[2] == (day, month):
            return hit[1]

    body = _compute_kpis(authorization, day, month)
    with _kpi_lock:
        _kpi_cache[uid] = (now + _KPI_TTL_SEC, body, (day, month))
    return body
