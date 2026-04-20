"""ARIA Phase 15 — God Mode CEO Dashboard.

Real-time business state narration with KPIs, pipeline health, revenue,
team performance, and client status — all on one screen.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _fetch_rows(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_sb(),
        params=params,
        timeout=20.0,
    )
    return r.json() if r.status_code < 400 else []


def _count_rows(table: str, filters: dict[str, str]) -> int:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb(), "Prefer": "count=exact"},
        params={**filters, "select": "id", "limit": "0"},
        timeout=15.0,
    )
    cr = r.headers.get("content-range", "")
    if "/" in cr:
        try:
            return int(cr.split("/")[1])
        except (ValueError, IndexError):
            pass
    return 0


def get_dashboard_data() -> dict[str, Any]:
    """Fetch all KPIs and metrics for the CEO God Mode dashboard."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"error": "Supabase not configured"}

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    # Revenue metrics
    clients = _fetch_rows("clients", {
        "status": "eq.active",
        "select": "id,mrr_cents,plan,created_at",
        "limit": "1000",
    })
    total_mrr = sum((c.get("mrr_cents") or 0) for c in clients) / 100
    total_arr = total_mrr * 12
    client_count = len(clients)

    plan_breakdown: dict[str, int] = {}
    for c in clients:
        plan = c.get("plan") or "unknown"
        plan_breakdown[plan] = plan_breakdown.get(plan, 0) + 1

    # Pipeline metrics
    prospect_stages = {}
    for stage in ["new", "scanned", "sent_email", "replied", "call_booked", "closed_won", "lost"]:
        prospect_stages[stage] = _count_rows("prospects", {"stage": f"eq.{stage}"})

    total_prospects = sum(prospect_stages.values())
    new_this_week = _count_rows("prospects", {"created_at": f"gte.{week_ago}"})

    # Activity metrics
    calls_today = _count_rows("activities", {
        "type": "eq.call",
        "created_at": f"gte.{today_start}",
    })
    emails_today = _count_rows("activities", {
        "type": "eq.email",
        "created_at": f"gte.{today_start}",
    })

    # Client health
    health_scores = _fetch_rows("aria_client_health_scores", {
        "select": "score,at_risk",
        "limit": "500",
    })
    at_risk_count = sum(1 for h in health_scores if h.get("at_risk"))
    avg_health = 0.0
    if health_scores:
        avg_health = sum((h.get("score") or 0) for h in health_scores) / len(health_scores)

    # Team metrics
    vas = _fetch_rows("profiles", {
        "role": "eq.va",
        "select": "id,full_name,status",
        "limit": "100",
    })
    active_vas = sum(1 for v in vas if v.get("status") == "active")

    # Pipeline runs
    recent_runs = _fetch_rows("aria_pipeline_runs", {
        "select": "id,status,leads_pulled,emails_sent,started_at",
        "order": "started_at.desc",
        "limit": "5",
    })

    # Inbound replies
    pending_replies = _count_rows("aria_inbound_replies", {"status": "eq.pending"})

    return {
        "timestamp": now.isoformat(),
        "revenue": {
            "mrr": round(total_mrr, 2),
            "arr": round(total_arr, 2),
            "active_clients": client_count,
            "plan_breakdown": plan_breakdown,
        },
        "pipeline": {
            "total_prospects": total_prospects,
            "new_this_week": new_this_week,
            "stages": prospect_stages,
            "conversion_rate": round(
                (prospect_stages.get("closed_won", 0) / total_prospects * 100) if total_prospects > 0 else 0, 1
            ),
        },
        "activity": {
            "calls_today": calls_today,
            "emails_today": emails_today,
            "target_calls": 24,
            "call_attainment": round((calls_today / 24) * 100, 1),
        },
        "client_health": {
            "average_score": round(avg_health, 1),
            "at_risk_count": at_risk_count,
            "total_scored": len(health_scores),
        },
        "team": {
            "active_vas": active_vas,
            "total_vas": len(vas),
        },
        "outbound": {
            "recent_pipeline_runs": recent_runs,
            "pending_replies": pending_replies,
        },
    }


def generate_narration(dashboard_data: dict[str, Any]) -> str:
    """Generate an AI narration of the current business state."""
    if not OPENAI_API_KEY:
        return _fallback_narration(dashboard_data)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are ARIA, the CEO's chief of staff at Hawk Security. "
                        "Narrate the current state of the business in 3-4 concise paragraphs. "
                        "Lead with the most important metric or trend. "
                        "Highlight anything that needs immediate attention. "
                        "Be direct, no fluff. Use numbers. "
                        "Target: 24 calls/day, healthy clients score > 50."
                    ),
                },
                {"role": "user", "content": json.dumps(dashboard_data)},
            ],
            max_tokens=800,
            temperature=0.4,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("Dashboard narration failed: %s", exc)
        return _fallback_narration(dashboard_data)


def _fallback_narration(data: dict[str, Any]) -> str:
    """Generate a basic narration without AI."""
    rev = data.get("revenue", {})
    pipe = data.get("pipeline", {})
    act = data.get("activity", {})
    health = data.get("client_health", {})

    lines = [
        f"**Revenue**: ${rev.get('mrr', 0):,.0f} MRR ({rev.get('active_clients', 0)} active clients).",
        f"**Pipeline**: {pipe.get('total_prospects', 0)} total prospects, {pipe.get('new_this_week', 0)} new this week.",
        f"**Today**: {act.get('calls_today', 0)}/{act.get('target_calls', 24)} calls booked ({act.get('call_attainment', 0)}% of target).",
        f"**Client Health**: avg {health.get('average_score', 0)}/100, {health.get('at_risk_count', 0)} at risk.",
    ]
    return "\n".join(lines)
