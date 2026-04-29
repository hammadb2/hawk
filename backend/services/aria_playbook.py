"""ARIA Phase 14 — Automatic sales playbook builder.

Analyzes email threads, call notes, and deal outcomes to build and refine
sales playbooks automatically. Identifies winning patterns and objection handling.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
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


def build_playbook_from_deals() -> dict[str, Any]:
    """Analyze won/lost deals and build a sales playbook.

    Examines prospect data, activities, and outcomes to identify patterns.
    """
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"error": "Supabase not configured"}

    # Fetch won deals
    won = _fetch_rows("prospects", {
        "stage": "eq.closed_won",
        "select": "id,company_name,vertical,contact_name,contact_email,city,created_at",
        "order": "created_at.desc",
        "limit": "50",
    })

    # Fetch lost deals
    lost = _fetch_rows("prospects", {
        "stage": "eq.lost",
        "select": "id,company_name,vertical,contact_name,city,created_at",
        "order": "created_at.desc",
        "limit": "50",
    })

    # Fetch recent activities for context
    activities = _fetch_rows("activities", {
        "select": "type,prospect_id,notes,created_at",
        "order": "created_at.desc",
        "limit": "200",
    })

    # Fetch inbound replies for objection patterns
    replies = _fetch_rows("aria_inbound_replies", {
        "select": "classification,original_reply,drafted_response,status",
        "order": "created_at.desc",
        "limit": "100",
    })

    # Build analysis input
    analysis_data = {
        "won_deals": len(won),
        "lost_deals": len(lost),
        "won_verticals": _count_by_key(won, "vertical"),
        "lost_verticals": _count_by_key(lost, "vertical"),
        "activity_types": _count_by_key(activities, "type"),
        "reply_classifications": _count_by_key(replies, "classification"),
        "sample_objections": [
            r.get("original_reply", "")[:200]
            for r in replies
            if r.get("classification") == "objection"
        ][:10],
        "sample_won_companies": [w.get("company_name", "") for w in won[:10]],
    }

    try:
        from services.openai_chat import chat_text_sync
        import re

        text = chat_text_sync(
            api_key=OPENAI_API_KEY,
            system=(
                "You are a sales strategist for Hawk Security, a US cybersecurity company "
                "serving small US professional practices — dental clinics, law firms, and accounting / CPA firms. "
                "Products (USD): HAWK Core $249/mo, HAWK Guard $449/mo, HAWK Sentinel $799/mo. "
                "Differentiators: HAWK Certified badge, Breach Response Guarantee ($250k / $1M / $2.5M by tier), "
                "vertical-specific US compliance artifacts (HIPAA risk analysis, FTC Safeguards WISP, ABA Opinion 24-514 workbook). "
                "Build a comprehensive sales playbook from the deal data. "
                "Return JSON: {\"playbook\": {\"title\": \"...\", \"updated_at\": \"...\", "
                "\"ideal_customer_profile\": {\"verticals\": [...], \"company_size\": \"...\", "
                "\"decision_maker\": \"...\", \"pain_points\": [...]}, "
                "\"winning_patterns\": [{\"pattern\": \"...\", \"frequency\": \"...\"}], "
                "\"objection_handlers\": [{\"objection\": \"...\", \"response\": \"...\"}], "
                "\"email_templates\": [{\"name\": \"...\", \"subject\": \"...\", \"body\": \"...\"}], "
                "\"call_scripts\": [{\"stage\": \"...\", \"script\": \"...\"}], "
                "\"kpis\": [{\"metric\": \"...\", \"target\": \"...\"}]}}"
            ),
            user_messages=[{"role": "user", "content": json.dumps(analysis_data)}],
            max_tokens=3000,
        )

        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            playbook = json.loads(m.group(0))
            # Store playbook
            _store_playbook(playbook)
            return playbook
        return {"raw_playbook": text}
    except Exception as exc:
        logger.exception("Playbook generation failed: %s", exc)
        return {"error": str(exc)}


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        v = item.get(key) or "unknown"
        counts[v] = counts.get(v, 0) + 1
    return counts


def _store_playbook(playbook: dict[str, Any]) -> None:
    """Store generated playbook in the database."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return

    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_playbooks",
            headers=_sb(),
            json={
                "title": playbook.get("playbook", {}).get("title", "Sales Playbook"),
                "content": playbook,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=20.0,
        )
    except Exception as exc:
        logger.warning("Failed to store playbook: %s", exc)


def get_latest_playbook() -> dict[str, Any] | None:
    """Get the most recently generated playbook."""
    rows = _fetch_rows("aria_playbooks", {
        "select": "id,title,content,created_at",
        "order": "created_at.desc",
        "limit": "1",
    })
    return rows[0] if rows else None


def get_objection_handler(objection: str) -> dict[str, Any]:
    """Get a specific objection handling response using the playbook + AI."""
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}

    playbook = get_latest_playbook()
    playbook_context = ""
    if playbook:
        handlers = playbook.get("content", {}).get("playbook", {}).get("objection_handlers", [])
        if handlers:
            playbook_context = "Known objection handlers:\n" + json.dumps(handlers[:10])

    try:
        from services.openai_chat import chat_text_sync

        reply = chat_text_sync(
            api_key=OPENAI_API_KEY,
            system=(
                "You are a sales coach for Hawk Security. "
                "Help handle this prospect objection using the playbook context. "
                "Be direct and provide a ready-to-use response. "
                f"{playbook_context}"
            ),
            user_messages=[{"role": "user", "content": f"Prospect objection: {objection}"}],
            max_tokens=500,
        )

        return {"response": reply}
    except Exception as exc:
        return {"error": str(exc)}
