"""ARIA Phase 3 — Client health score calculation (0–100).

Runs every 15 minutes via cron. Scores each active client based on:
- Scan recency and severity (latest HAWK score, days since last scan)
- Activity recency (last CRM activity)
- MRR tier (higher MRR clients weighted more)
- Open critical/high findings count

Flags clients at_risk when score < 50.  Inserts a CRM notification for
CEO/HoS when a client newly drops below the threshold.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

AT_RISK_THRESHOLD = 50


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _compute_client_health(
    *,
    hawk_score: int,
    days_since_scan: int,
    days_since_activity: int,
    mrr_cents: int,
    open_critical: int,
    open_high: int,
    status: str,
) -> tuple[int, dict[str, Any]]:
    """Return (score, factors_dict)."""
    score = 80  # base

    # Hawk score component (0–100 mapped to -20..+15)
    if hawk_score >= 80:
        score += 15
    elif hawk_score >= 60:
        score += 5
    elif hawk_score >= 40:
        score -= 5
    else:
        score -= 20

    # Scan freshness
    if days_since_scan <= 7:
        score += 5
    elif days_since_scan <= 30:
        score += 0
    elif days_since_scan <= 90:
        score -= 10
    else:
        score -= 20

    # Activity freshness
    if days_since_activity <= 7:
        score += 5
    elif days_since_activity <= 30:
        score += 0
    elif days_since_activity <= 60:
        score -= 5
    else:
        score -= 15

    # Open findings penalty
    score -= min(20, open_critical * 8)
    score -= min(10, open_high * 3)

    # MRR bonus (higher-value clients get slight boost for engagement tracking priority)
    if mrr_cents >= 250000:  # Enterprise $2,500+
        score += 5
    elif mrr_cents >= 99700:  # Shield $997+
        score += 2

    # Past due / churned penalty
    if status == "past_due":
        score -= 15
    elif status == "churned":
        score -= 30

    score = max(0, min(100, score))

    factors = {
        "hawk_score": hawk_score,
        "days_since_scan": days_since_scan,
        "days_since_activity": days_since_activity,
        "mrr_cents": mrr_cents,
        "open_critical": open_critical,
        "open_high": open_high,
        "status": status,
    }
    return score, factors


def run_client_health_scores() -> dict[str, Any]:
    """Calculate and upsert health scores for all active clients."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured", "updated": 0}

    headers = _sb()
    now = datetime.now(timezone.utc)

    # 1. Fetch all active/past_due clients
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=headers,
        params={
            "select": "id,prospect_id,domain,company_name,mrr_cents,status",
            "status": "neq.churned",
            "limit": "500",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("client fetch failed: %s", r.text[:300])
        return {"ok": False, "error": r.text[:300]}
    clients: list[dict[str, Any]] = r.json() or []

    if not clients:
        return {"ok": True, "updated": 0, "at_risk": 0, "message": "no active clients"}

    # 2. Fetch latest scan per prospect (for hawk_score + scan date)
    prospect_ids = [c["prospect_id"] for c in clients if c.get("prospect_id")]
    scan_data: dict[str, dict[str, Any]] = {}
    if prospect_ids:
        sr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=headers,
            params={
                "select": "id,hawk_score,last_activity_at",
                "id": f"in.({','.join(prospect_ids)})",
                "limit": "500",
            },
            timeout=30.0,
        )
        if sr.status_code < 400:
            for row in sr.json() or []:
                scan_data[row["id"]] = row

    # 3. Fetch activities for each client (most recent)
    activity_data: dict[str, str] = {}
    client_ids = [c["id"] for c in clients]
    if client_ids:
        ar = httpx.get(
            f"{SUPABASE_URL}/rest/v1/activities",
            headers=headers,
            params={
                "select": "client_id,created_at",
                "client_id": f"in.({','.join(client_ids)})",
                "order": "created_at.desc",
                "limit": "500",
            },
            timeout=30.0,
        )
        if ar.status_code < 400:
            for row in ar.json() or []:
                cid = row.get("client_id")
                if cid and cid not in activity_data:
                    activity_data[cid] = row["created_at"]

    # 4. Fetch existing health scores to detect newly at-risk
    existing_scores: dict[str, dict[str, Any]] = {}
    er = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_client_health_scores",
        headers=headers,
        params={"select": "client_id,score,at_risk", "limit": "500"},
        timeout=30.0,
    )
    if er.status_code < 400:
        for row in er.json() or []:
            existing_scores[row["client_id"]] = row

    # 5. Compute and upsert scores
    updated = 0
    at_risk_count = 0
    newly_at_risk: list[dict[str, Any]] = []

    for client in clients:
        cid = client["id"]
        pid = client.get("prospect_id")
        prospect = scan_data.get(pid, {}) if pid else {}

        hawk_score = prospect.get("hawk_score", 0) or 0

        # Days since last scan (use prospect last_activity_at as proxy)
        last_scan_str = prospect.get("last_activity_at")
        if last_scan_str:
            try:
                last_scan = datetime.fromisoformat(str(last_scan_str).replace("Z", "+00:00"))
                if last_scan.tzinfo is None:
                    last_scan = last_scan.replace(tzinfo=timezone.utc)
                days_since_scan = (now - last_scan).days
            except Exception:
                days_since_scan = 999
        else:
            days_since_scan = 999

        # Days since last CRM activity
        last_act_str = activity_data.get(cid)
        if last_act_str:
            try:
                last_act = datetime.fromisoformat(str(last_act_str).replace("Z", "+00:00"))
                if last_act.tzinfo is None:
                    last_act = last_act.replace(tzinfo=timezone.utc)
                days_since_activity = (now - last_act).days
            except Exception:
                days_since_activity = 999
        else:
            days_since_activity = 999

        score, factors = _compute_client_health(
            hawk_score=hawk_score,
            days_since_scan=days_since_scan,
            days_since_activity=days_since_activity,
            mrr_cents=client.get("mrr_cents", 0) or 0,
            open_critical=0,  # TODO: wire to findings count in future
            open_high=0,
            status=client.get("status", "active"),
        )

        at_risk = score < AT_RISK_THRESHOLD
        if at_risk:
            at_risk_count += 1

        # Check if newly at-risk
        prev = existing_scores.get(cid)
        if at_risk and (not prev or not prev.get("at_risk")):
            newly_at_risk.append({
                "client_id": cid,
                "company_name": client.get("company_name") or client.get("domain") or cid,
                "score": score,
                "factors": factors,
            })

        # Upsert into aria_client_health_scores
        payload = {
            "client_id": cid,
            "score": score,
            "factors": factors,
            "at_risk": at_risk,
            "updated_at": now.isoformat(),
        }

        if prev:
            # Update existing
            pr = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/aria_client_health_scores",
                headers=headers,
                params={"client_id": f"eq.{cid}"},
                json=payload,
                timeout=15.0,
            )
        else:
            # Insert new
            pr = httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_client_health_scores",
                headers={**headers, "Prefer": "return=minimal"},
                json=payload,
                timeout=15.0,
            )

        if pr.status_code < 400:
            updated += 1
        else:
            logger.warning("health score upsert failed client=%s: %s", cid, pr.text[:200])

    # 6. Create notifications for newly at-risk clients
    if newly_at_risk:
        _create_at_risk_notifications(headers, newly_at_risk)

    return {
        "ok": True,
        "updated": updated,
        "at_risk": at_risk_count,
        "newly_at_risk": len(newly_at_risk),
        "total_clients": len(clients),
    }


def _create_at_risk_notifications(headers: dict[str, str], at_risk_clients: list[dict[str, Any]]) -> None:
    """Insert CRM notifications for CEO/HoS about newly at-risk clients."""
    # Fetch CEO and HoS profiles
    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={
            "select": "id,role",
            "role": "in.(ceo,hos)",
            "limit": "20",
        },
        timeout=15.0,
    )
    if pr.status_code >= 400:
        return

    notify_users = [row["id"] for row in (pr.json() or [])]
    if not notify_users:
        return

    for client in at_risk_clients:
        company = client["company_name"]
        score = client["score"]
        for uid in notify_users:
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/notifications",
                headers={**headers, "Prefer": "return=minimal"},
                json={
                    "user_id": uid,
                    "title": f"Client at risk: {company}",
                    "message": f"{company} health score dropped to {score}/100. Review in ARIA.",
                    "type": "warning",
                    "link": "/crm/ai",
                },
                timeout=15.0,
            )
