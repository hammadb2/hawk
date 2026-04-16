"""ARIA Phase 3 — Proactive briefing generation.

Monday morning CEO/HoS briefing: revenue snapshot, calls booked yesterday,
VA standings, cold prospects, clients up for renewal, active alerts.

Weekly competitive brief for CEO only.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from services.openai_chat import chat_text_sync

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


def _fetch_metrics(headers: dict[str, str]) -> dict[str, Any]:
    """Gather live metrics for briefing content."""
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).date().isoformat()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    metrics: dict[str, Any] = {}

    # Active clients + MRR
    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=headers,
        params={"select": "id,mrr_cents,status,plan", "status": "eq.active", "limit": "500"},
        timeout=30.0,
    )
    if cr.status_code < 400:
        clients = cr.json() or []
        metrics["active_clients"] = len(clients)
        metrics["mrr_cents"] = sum(c.get("mrr_cents", 0) or 0 for c in clients)
        metrics["mrr_display"] = f"${metrics['mrr_cents'] / 100:,.0f}"
        metrics["plan_breakdown"] = {}
        for c in clients:
            plan = c.get("plan") or "unknown"
            metrics["plan_breakdown"][plan] = metrics["plan_breakdown"].get(plan, 0) + 1

    # Prospects by stage
    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=headers,
        params={"select": "id,stage", "limit": "2000"},
        timeout=30.0,
    )
    if pr.status_code < 400:
        prospects = pr.json() or []
        stage_counts: dict[str, int] = {}
        for p in prospects:
            stage = p.get("stage") or "unknown"
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        metrics["prospect_stages"] = stage_counts
        metrics["total_prospects"] = len(prospects)
        metrics["pipeline_active"] = sum(
            v for k, v in stage_counts.items() if k not in ("lost", "closed_won")
        )

    # Calls booked yesterday (prospects that moved to call_booked stage)
    ar = httpx.get(
        f"{SUPABASE_URL}/rest/v1/activities",
        headers=headers,
        params={
            "select": "id",
            "type": "eq.stage_change",
            "created_at": f"gte.{yesterday}T00:00:00Z",
            "limit": "200",
        },
        timeout=30.0,
    )
    if ar.status_code < 400:
        metrics["activities_yesterday"] = len(ar.json() or [])

    # At-risk clients
    hr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_client_health_scores",
        headers=headers,
        params={"select": "client_id,score", "at_risk": "eq.true", "limit": "50"},
        timeout=15.0,
    )
    if hr.status_code < 400:
        at_risk = hr.json() or []
        metrics["at_risk_clients"] = len(at_risk)
    else:
        metrics["at_risk_clients"] = 0

    # Closes this month
    clr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=headers,
        params={
            "select": "id,mrr_cents",
            "close_date": f"gte.{start_of_month}",
            "limit": "100",
        },
        timeout=15.0,
    )
    if clr.status_code < 400:
        closes = clr.json() or []
        metrics["closes_mtd"] = len(closes)
        metrics["new_mrr_mtd_cents"] = sum(c.get("mrr_cents", 0) or 0 for c in closes)

    # VA count (profiles with role = va or role_type = va)
    vr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"select": "id", "role_type": "eq.va", "limit": "100"},
        timeout=15.0,
    )
    if vr.status_code < 400:
        metrics["active_vas"] = len(vr.json() or [])

    return metrics


def generate_monday_briefing(metrics: dict[str, Any]) -> str:
    """Generate a Monday morning briefing using OpenAI."""
    today_str = date.today().isoformat()

    if not OPENAI_API_KEY:
        # Fallback: structured text without AI
        return _build_fallback_briefing(metrics, today_str)

    metrics_json = json.dumps(metrics, indent=2, default=str)

    prompt = f"""Generate a concise Monday morning business briefing for the CEO of Hawk Security.
Today is {today_str}.

Here are the live metrics:
{metrics_json}

HAWK SECURITY CONTEXT:
- Canadian cybersecurity company targeting dental clinics, law firms, and accounting practices
- Three products: Starter $199/mo, Shield $997/mo, Enterprise $2,500/mo
- Target: 24 booked sales calls per day from cold email outreach
- VA team runs the outbound pipeline

FORMAT:
- Start with a one-line status summary (e.g. "Strong week — MRR up, pipeline healthy")
- Revenue section: current MRR, closes this month, new MRR added
- Pipeline section: active prospects by stage, calls booked trend
- Team section: active VAs, any rep health alerts
- Risk section: at-risk clients count and recommended actions
- End with 2-3 priority actions for the week

Be direct and data-driven. No fluff. Use markdown formatting."""

    return chat_text_sync(
        api_key=OPENAI_API_KEY,
        system="You are ARIA, Hawk Security's chief of staff. Sharp, confident, concise. Present data cleanly.",
        user_messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
    )


def _build_fallback_briefing(metrics: dict[str, Any], today_str: str) -> str:
    """Structured briefing without AI."""
    mrr = metrics.get("mrr_display", "$0")
    active = metrics.get("active_clients", 0)
    pipeline = metrics.get("pipeline_active", 0)
    at_risk = metrics.get("at_risk_clients", 0)
    closes_mtd = metrics.get("closes_mtd", 0)
    vas = metrics.get("active_vas", 0)

    return f"""## Monday Briefing — {today_str}

**Revenue:** {mrr} MRR across {active} active clients. {closes_mtd} closes this month.

**Pipeline:** {pipeline} active prospects in pipeline.

**Team:** {vas} active VAs.

**Risk:** {at_risk} clients flagged at-risk. Review in ARIA.

*Configure OPENAI_API_KEY for AI-generated insights.*"""


def generate_competitive_brief() -> str:
    """Weekly competitive intelligence brief for CEO."""
    today_str = date.today().isoformat()

    if not OPENAI_API_KEY:
        return f"## Competitive Brief — {today_str}\n\nConfigure OPENAI_API_KEY for AI-generated competitive intelligence."

    prompt = f"""Generate a weekly competitive intelligence brief for the CEO of Hawk Security.
Today is {today_str}.

HAWK SECURITY CONTEXT:
- Canadian cybersecurity company targeting dental clinics, law firms, and accounting practices
- Three products: Starter $199/mo, Shield $997/mo, Enterprise $2,500/mo
- Competitors include generic MSPs, larger cybersecurity firms, and DIY security tools
- Key differentiators: HAWK Certified badge, financial guarantee, PIPEDA compliance focus

Write a brief covering:
1. Notable cybersecurity threats affecting Canadian SMBs this week
2. Competitive landscape shifts (MSP market, SMB security adoption trends)
3. Regulatory developments (PIPEDA, Bill C-26, provincial privacy laws)
4. 1-2 strategic recommendations

Keep it to 3-4 paragraphs. Be specific and actionable. Markdown format."""

    return chat_text_sync(
        api_key=OPENAI_API_KEY,
        system="You are ARIA, Hawk Security's chief of staff providing competitive intelligence. Direct and strategic.",
        user_messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
    )


def run_monday_briefing() -> dict[str, Any]:
    """Generate and store Monday briefings for CEO and HoS users."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}

    headers = _sb()
    today = date.today()

    # Check if Monday briefing already generated today (exclude competitive briefs)
    existing = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_proactive_briefings",
        headers=headers,
        params={
            "briefing_date": f"eq.{today.isoformat()}",
            "content": "not.like.## Competitive Intelligence*",
            "select": "id",
            "limit": "1",
        },
        timeout=15.0,
    )
    if existing.status_code < 400 and (existing.json() or []):
        return {"ok": True, "skipped": True, "message": "monday briefing already generated today"}

    # Gather metrics and generate briefing
    metrics = _fetch_metrics(headers)
    briefing_content = generate_monday_briefing(metrics)

    # Find CEO and HoS users
    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"select": "id,role", "role": "in.(ceo,hos)", "limit": "20"},
        timeout=15.0,
    )
    if pr.status_code >= 400:
        return {"ok": False, "error": "failed to fetch profiles"}

    users = pr.json() or []
    stored = 0

    for user in users:
        uid = user["id"]
        payload = {
            "user_id": uid,
            "briefing_date": today.isoformat(),
            "content": briefing_content,
            "read": False,
        }
        sr = httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_proactive_briefings",
            headers={**headers, "Prefer": "return=minimal"},
            json=payload,
            timeout=15.0,
        )
        if sr.status_code < 400:
            stored += 1
        else:
            logger.warning("briefing store failed user=%s: %s", uid, sr.text[:200])

    # Also create a notification
    for user in users:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/notifications",
            headers={**headers, "Prefer": "return=minimal"},
            json={
                "user_id": user["id"],
                "title": "Monday Briefing Ready",
                "message": "Your weekly business briefing from ARIA is ready. Open ARIA to review.",
                "type": "info",
                "link": "/crm/ai",
            },
            timeout=15.0,
        )

    return {"ok": True, "briefings_stored": stored, "users": len(users)}


def run_competitive_brief() -> dict[str, Any]:
    """Generate and store weekly competitive brief for CEO."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}

    headers = _sb()
    today = date.today()

    # Check if competitive brief already generated today
    existing = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_proactive_briefings",
        headers=headers,
        params={
            "briefing_date": f"eq.{today.isoformat()}",
            "content": "like.## Competitive Intelligence*",
            "select": "id",
            "limit": "1",
        },
        timeout=15.0,
    )
    if existing.status_code < 400 and (existing.json() or []):
        return {"ok": True, "skipped": True, "message": "competitive brief already generated today"}

    brief_content = generate_competitive_brief()

    # Store for CEO only
    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"select": "id", "role": "eq.ceo", "limit": "5"},
        timeout=15.0,
    )
    if pr.status_code >= 400:
        return {"ok": False, "error": "failed to fetch CEO profiles"}

    ceos = pr.json() or []
    stored = 0

    for ceo in ceos:
        payload = {
            "user_id": ceo["id"],
            "briefing_date": today.isoformat(),
            "content": f"## Competitive Intelligence\n\n{brief_content}",
            "read": False,
        }
        sr = httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_proactive_briefings",
            headers={**headers, "Prefer": "return=minimal"},
            json=payload,
            timeout=15.0,
        )
        if sr.status_code < 400:
            stored += 1

    return {"ok": True, "briefs_stored": stored}
