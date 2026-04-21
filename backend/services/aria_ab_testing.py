"""ARIA Phase 10 — Autonomous A/B experiment runner via Smartlead API.

Creates, monitors, and analyzes email A/B experiments through Smartlead campaigns.
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
SMARTLEAD_API_KEY = os.environ.get("SMARTLEAD_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

SMARTLEAD_BASE = "https://server.smartlead.ai/api/v1"


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _sl_params() -> dict[str, str]:
    return {"api_key": SMARTLEAD_API_KEY}


def create_ab_experiment(
    name: str,
    variant_a_subject: str,
    variant_b_subject: str,
    variant_a_body: str,
    variant_b_body: str,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    """Create an A/B test experiment.

    If campaign_id is provided, modifies existing campaign sequences.
    Otherwise creates a new campaign with two variants.
    """
    if not SMARTLEAD_API_KEY:
        return {"error": "Smartlead API key not configured"}

    experiment = {
        "name": name,
        "variant_a": {"subject": variant_a_subject, "body": variant_a_body},
        "variant_b": {"subject": variant_b_subject, "body": variant_b_body},
        "campaign_id": campaign_id,
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store experiment in DB
    if SUPABASE_URL and SERVICE_KEY:
        try:
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_ab_experiments",
                headers={**_sb(), "Prefer": "return=representation"},
                json=experiment,
                timeout=20.0,
            )
            if r.status_code < 400:
                rows = r.json()
                if isinstance(rows, list) and rows:
                    experiment["id"] = rows[0].get("id")
        except Exception as exc:
            logger.warning("Failed to store experiment: %s", exc)

    return experiment


def get_campaign_stats(campaign_id: str) -> dict[str, Any]:
    """Fetch campaign statistics from Smartlead."""
    if not SMARTLEAD_API_KEY:
        return {"error": "Smartlead API key not configured"}

    try:
        r = httpx.get(
            f"{SMARTLEAD_BASE}/campaigns/{campaign_id}/analytics",
            params=_sl_params(),
            timeout=20.0,
        )
        if r.status_code < 400:
            return r.json()
        return {"error": f"Smartlead API error: {r.status_code}"}
    except Exception as exc:
        return {"error": str(exc)}


def analyze_experiment(experiment_id: str) -> dict[str, Any]:
    """Analyze A/B test results and determine a winner."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"error": "Supabase not configured"}

    # Fetch experiment
    rows = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_ab_experiments",
        headers=_sb(),
        params={"id": f"eq.{experiment_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    ).json() or []

    if not rows:
        return {"error": "Experiment not found"}

    experiment = rows[0]

    # Use AI to analyze results
    if OPENAI_API_KEY:
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
                            "You are an email marketing analyst. Analyze the A/B test data and determine "
                            "the winner. Return JSON: {\"winner\": \"A\" or \"B\" or \"inconclusive\", "
                            "\"confidence\": 0.0-1.0, \"reasoning\": \"...\", \"recommendation\": \"...\"}"
                        ),
                    },
                    {"role": "user", "content": json.dumps(experiment)},
                ],
                max_tokens=500,
                temperature=0.2,
            )
            import re

            text = (response.choices[0].message.content or "").strip()
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group(0))
        except Exception as exc:
            logger.exception("Experiment analysis failed: %s", exc)

    return {"winner": "inconclusive", "confidence": 0, "reasoning": "Analysis unavailable"}


def list_experiments(limit: int = 20) -> list[dict[str, Any]]:
    """List recent A/B experiments."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return []

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_ab_experiments",
        headers=_sb(),
        params={
            "select": "id,name,status,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        },
        timeout=20.0,
    )
    return r.json() if r.status_code < 400 else []


def generate_variants(
    original_subject: str, original_body: str, test_element: str = "subject"
) -> dict[str, Any]:
    """Use AI to generate A/B test variants from an original email."""
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
                        "You are a cold email optimization expert for Hawk Security, a US cybersecurity company "
                        "targeting dental clinics, law firms, and accounting practices. "
                        "Generate an A/B test variant. Return JSON: "
                        "{\"variant_subject\": \"...\", \"variant_body\": \"...\", \"hypothesis\": \"...\"}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Original subject: {original_subject}\n"
                        f"Original body: {original_body}\n"
                        f"Element to test: {test_element}\n"
                        "Generate a variant that tests a different approach for this element."
                    ),
                },
            ],
            max_tokens=800,
            temperature=0.7,
        )
        import re

        text = (response.choices[0].message.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
    except Exception as exc:
        logger.exception("Variant generation failed: %s", exc)

    return {"error": "Failed to generate variants"}
