"""ARIA Phase 9 — Business pattern learning and causal insights.

Detects behavioral patterns from CRM activity and surfaces proactive insights.
Stores patterns in aria_user_patterns for CEO/HoS reference.
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
    if r.status_code >= 400:
        return []
    return r.json() or []


def detect_patterns() -> list[dict[str, Any]]:
    """Analyze recent CRM activity and detect business patterns.

    Returns a list of pattern objects with type, description, and confidence.
    """
    if not SUPABASE_URL or not SERVICE_KEY or not OPENAI_API_KEY:
        return []

    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    # Gather recent data points
    recent_activities = _fetch_rows("activities", {
        "created_at": f"gte.{week_ago}",
        "select": "type,created_at",
        "limit": "500",
    })

    recent_prospects = _fetch_rows("prospects", {
        "created_at": f"gte.{month_ago}",
        "select": "stage,vertical,created_at",
        "limit": "300",
    })

    health_scores = _fetch_rows("aria_client_health_scores", {
        "select": "score,at_risk,updated_at",
        "limit": "200",
    })

    # Aggregate metrics
    activity_types: dict[str, int] = {}
    for a in recent_activities:
        t = a.get("type", "unknown")
        activity_types[t] = activity_types.get(t, 0) + 1

    stage_counts: dict[str, int] = {}
    vertical_counts: dict[str, int] = {}
    for p in recent_prospects:
        s = p.get("stage", "unknown")
        stage_counts[s] = stage_counts.get(s, 0) + 1
        v = p.get("vertical", "unknown")
        vertical_counts[v] = vertical_counts.get(v, 0) + 1

    at_risk = sum(1 for h in health_scores if h.get("at_risk"))
    avg_health = 0.0
    if health_scores:
        avg_health = sum(h.get("score") or 0 for h in health_scores) / len(health_scores)

    data_summary = {
        "activity_types_this_week": activity_types,
        "prospect_stages_this_month": stage_counts,
        "prospect_verticals_this_month": vertical_counts,
        "client_health_avg": round(avg_health, 1),
        "clients_at_risk": at_risk,
        "total_clients_scored": len(health_scores),
    }

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
                        "You are a business intelligence analyst for Hawk Security, a US cybersecurity company serving small US professional practices (dental, legal, accounting / CPA). "
                        "Analyze the CRM data and identify actionable business patterns. "
                        "Return valid JSON only: {\"patterns\": [{\"type\": \"...\", \"title\": \"...\", "
                        "\"description\": \"...\", \"confidence\": 0.0-1.0, \"action\": \"...\"}]}. "
                        "Types: conversion_trend, churn_risk, engagement_spike, pipeline_bottleneck, "
                        "vertical_opportunity, seasonal_pattern. Max 5 patterns."
                    ),
                },
                {"role": "user", "content": json.dumps(data_summary)},
            ],
            max_tokens=1500,
            temperature=0.3,
        )

        text = (response.choices[0].message.content or "").strip()
        # Parse JSON from response
        import re

        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            parsed = json.loads(m.group(0))
            return parsed.get("patterns", [])
    except Exception as exc:
        logger.exception("Pattern detection failed: %s", exc)

    return []


def store_patterns(patterns: list[dict[str, Any]]) -> int:
    """Store detected patterns in aria_user_patterns. Returns count stored."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return 0

    stored = 0
    now = datetime.now(timezone.utc).isoformat()

    for p in patterns:
        try:
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_user_patterns",
                headers=_sb(),
                json={
                    "pattern_key": p.get("type", "unknown"),
                    "pattern_value": p,
                    "updated_at": now,
                },
                timeout=15.0,
            )
            if r.status_code < 400:
                stored += 1
        except Exception as exc:
            logger.warning("Failed to store pattern: %s", exc)

    return stored


def get_recent_patterns(limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve recent stored patterns."""
    return _fetch_rows("aria_user_patterns", {
        "select": "id,pattern_key,pattern_value,updated_at",
        "order": "updated_at.desc",
        "limit": str(limit),
    })


def run_pattern_detection() -> dict[str, Any]:
    """Full pipeline: detect + store + return summary."""
    patterns = detect_patterns()
    stored = store_patterns(patterns) if patterns else 0
    return {
        "patterns_detected": len(patterns),
        "patterns_stored": stored,
        "patterns": patterns,
    }
