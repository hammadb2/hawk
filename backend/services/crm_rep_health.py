"""Phase 4 — Daily rep health score 0–100 (closers + sales reps)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import CRM_CEO_PHONE_E164
from services.crm_openphone import send_sms

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _compute_score(
    *,
    stale_7d: int,
    hot_recent: int,
    closes_mtd: int,
    reply_backlog: int,
) -> int:
    score = 72
    score -= min(36, stale_7d * 4)
    score += min(14, hot_recent * 3)
    score += min(22, closes_mtd * 6)
    score -= min(24, reply_backlog * 5)
    return max(0, min(100, score))


def run_rep_health_scores() -> dict[str, Any]:
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured", "updated": 0}

    now = datetime.now(timezone.utc)
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cutoff_stale = (now - timedelta(days=7)).isoformat()
    cutoff_hot = (now - timedelta(hours=48)).isoformat()

    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb(),
        params={
            "select": "id,assigned_rep_id,stage,last_activity_at,is_hot,reply_received_at,va_actioned_at",
            "limit": "2000",
        },
        timeout=60.0,
    )
    pr.raise_for_status()
    prospects: list[dict[str, Any]] = pr.json() or []

    cl = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={
            "close_date": f"gte.{start_month.isoformat()}",
            "select": "closing_rep_id",
            "limit": "2000",
        },
        timeout=60.0,
    )
    cl.raise_for_status()
    closes_mtd_by_rep: dict[str, int] = {}
    for row in cl.json() or []:
        rid = row.get("closing_rep_id")
        if rid:
            closes_mtd_by_rep[str(rid)] = closes_mtd_by_rep.get(str(rid), 0) + 1

    rep_ids: set[str] = set()
    for p in prospects:
        r = p.get("assigned_rep_id")
        if r:
            rep_ids.add(str(r))

    prof = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb(),
        params={"select": "id,role,full_name", "limit": "500"},
        timeout=60.0,
    )
    prof.raise_for_status()
    sales_roles = {"sales_rep", "closer", "team_lead"}
    prof_rows: list[dict[str, Any]] = prof.json() or []
    eligible = {str(r["id"]) for r in prof_rows if (r.get("role") or "") in sales_roles}
    name_by_id = {str(r["id"]): (r.get("full_name") or r.get("id")) for r in prof_rows}

    updated = 0
    alerts = 0

    for rid in sorted(rep_ids & eligible):
        assigned = [p for p in prospects if str(p.get("assigned_rep_id") or "") == rid]
        open_assigned = [p for p in assigned if (p.get("stage") or "") not in ("lost", "closed_won")]
        stale_7d = 0
        hot_recent = 0
        reply_backlog = 0
        for p in open_assigned:
            la_s = p.get("last_activity_at")
            la_str = str(la_s) if la_s is not None else ""
            if not la_str or la_str < cutoff_stale:
                stale_7d += 1
            if p.get("is_hot") and la_str and la_str >= cutoff_hot:
                hot_recent += 1
            if p.get("reply_received_at") and not p.get("va_actioned_at"):
                reply_backlog += 1

        closes_mtd = closes_mtd_by_rep.get(rid, 0)
        hs = _compute_score(
            stale_7d=stale_7d,
            hot_recent=hot_recent,
            closes_mtd=closes_mtd,
            reply_backlog=reply_backlog,
        )

        patch = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_sb(),
            params={"id": f"eq.{rid}"},
            json={"health_score": hs},
            timeout=20.0,
        )
        if patch.status_code < 400:
            updated += 1
        else:
            logger.warning("health_score patch failed %s: %s", rid, patch.text[:200])

        if hs < 50:
            name = name_by_id.get(rid, rid)
            try:
                send_sms(
                    CRM_CEO_PHONE_E164 or "+18259458282",
                    f"HAWK — Rep health alert\n{name} dropped to {hs}/100.\n"
                    f"Stale 7d+ open: {stale_7d}, reply backlog: {reply_backlog}, closes MTD: {closes_mtd}.",
                )
                alerts += 1
            except Exception:
                logger.exception("CEO rep health SMS failed")

    return {"ok": True, "updated": updated, "ceo_alerts": alerts, "reps_considered": len(rep_ids & eligible)}
