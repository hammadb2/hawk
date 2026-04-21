"""ARIA Phase 11 — Competitive intelligence layer via OpenAI web search.

Gathers competitive intelligence about cybersecurity market, competitor offerings,
and industry trends relevant to Hawk Security's target verticals.
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


def research_competitors(query: str | None = None) -> dict[str, Any]:
    """Research competitors and market landscape using OpenAI with web search.

    If no query is provided, uses a default Hawk Security competitive analysis query.
    """
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}

    default_query = (
        "US cybersecurity companies targeting small professional-practice SMBs (dental clinics, law firms, accounting / CPA firms). "
        "What are the main competitors, their pricing, and key differentiators? "
        "Focus on managed security services, vulnerability scanning, and US compliance (HIPAA Security Rule, FTC Safeguards Rule, ABA Formal Opinion 24-514)."
    )

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
                        "You are a competitive intelligence analyst for Hawk Security, a US cybersecurity company. "
                        "Hawk targets US dental clinics, law firms, and accounting / CPA practices with three tiers (USD): "
                        "HAWK Core ($249/mo), HAWK Guard ($449/mo), HAWK Sentinel ($799/mo). "
                        "Key differentiators: HAWK Certified badge, Breach Response Guarantee ($250k / $1M / $2.5M by tier), "
                        "US compliance artifacts (HIPAA / FTC Safeguards WISP / ABA Opinion 24-514 workbook). "
                        "Analyze the competitive landscape and provide actionable intelligence. "
                        "Return JSON: {\"competitors\": [{\"name\": \"...\", \"url\": \"...\", \"pricing\": \"...\", "
                        "\"strengths\": [\"...\"], \"weaknesses\": [\"...\"]}], "
                        "\"market_trends\": [\"...\"], \"opportunities\": [\"...\"], \"threats\": [\"...\"], "
                        "\"recommendation\": \"...\"}"
                    ),
                },
                {"role": "user", "content": query or default_query},
            ],
            max_tokens=2000,
            temperature=0.3,
        )

        import re

        text = (response.choices[0].message.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        return {"raw_analysis": text}
    except Exception as exc:
        logger.exception("Competitive research failed: %s", exc)
        return {"error": str(exc)}


def analyze_competitor_pricing(vertical: str = "dental") -> dict[str, Any]:
    """Analyze competitor pricing for a specific vertical."""
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}

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
                        "You are a pricing strategy analyst for Hawk Security. "
                        "Return JSON: {\"vertical\": \"...\", \"hawk_position\": \"...\", "
                        "\"competitor_range\": {\"low\": 0, \"mid\": 0, \"high\": 0}, "
                        "\"recommendation\": \"...\", \"talking_points\": [\"...\"]}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Analyze cybersecurity pricing for US {vertical} practices. "
                        f"Hawk offers (USD): HAWK Core $249/mo, HAWK Guard $449/mo, HAWK Sentinel $799/mo. "
                        f"How does this compare to competitors?"
                    ),
                },
            ],
            max_tokens=1000,
            temperature=0.3,
        )

        import re

        text = (response.choices[0].message.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        return {"raw_analysis": text}
    except Exception as exc:
        logger.exception("Pricing analysis failed: %s", exc)
        return {"error": str(exc)}


def store_intel_report(report: dict[str, Any]) -> str | None:
    """Store a competitive intelligence report in the database."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return None

    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_competitive_intel",
            headers={**_sb(), "Prefer": "return=representation"},
            json={
                "report_type": report.get("report_type", "competitive_analysis"),
                "content": report,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=20.0,
        )
        if r.status_code < 400:
            rows = r.json()
            if isinstance(rows, list) and rows:
                return rows[0].get("id")
    except Exception as exc:
        logger.warning("Failed to store intel report: %s", exc)

    return None


def get_latest_intel(limit: int = 5) -> list[dict[str, Any]]:
    """Get the latest competitive intelligence reports."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return []

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_competitive_intel",
        headers=_sb(),
        params={
            "select": "id,report_type,content,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        },
        timeout=20.0,
    )
    return r.json() if r.status_code < 400 else []
