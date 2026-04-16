"""ARIA Phase 19 — Onboarding trainer roleplay.

Interactive training mode where ARIA simulates sales scenarios, objection handling,
and product knowledge quizzes for new team members.
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


SCENARIO_TYPES = {
    "cold_call": {
        "title": "Cold Call Simulation",
        "description": "Practice cold calling a dental clinic owner about cybersecurity.",
        "persona": (
            "You are Dr. Sarah Chen, owner of Bright Smile Dental Clinic in Toronto. "
            "You have 12 employees and no IT staff. You've heard about cybersecurity "
            "but think it's only for big companies. You're busy and skeptical. "
            "Respond naturally as this persona would."
        ),
    },
    "objection_handling": {
        "title": "Objection Handling Practice",
        "description": "Handle common objections from prospects about cybersecurity services.",
        "persona": (
            "You are James Martinez, managing partner at Martinez & Associates Law Firm. "
            "You already pay for antivirus and think that's enough. You're price-sensitive "
            "and don't understand why you'd pay $199/month for cybersecurity. "
            "Push back with realistic objections."
        ),
    },
    "discovery_call": {
        "title": "Discovery Call Practice",
        "description": "Practice conducting a discovery call to uncover pain points.",
        "persona": (
            "You are Linda Park, office manager at Park Accounting Group. "
            "You're concerned about client data security after a competitor got breached. "
            "You're interested but need to convince your boss. "
            "Answer questions naturally and reveal pain points gradually."
        ),
    },
    "product_demo": {
        "title": "Product Demo Roleplay",
        "description": "Practice demonstrating Hawk Security products to a prospect.",
        "persona": (
            "You are Robert Kim, IT consultant for a group of dental offices. "
            "You're evaluating security solutions for 5 clinics. You're technical "
            "and will ask detailed questions about scanning methodology, compliance, "
            "and integration. Be impressed by good answers, skeptical of vague ones."
        ),
    },
    "upsell": {
        "title": "Upsell Conversation",
        "description": "Practice upselling a Starter client to Shield tier.",
        "persona": (
            "You are Maria Santos, owner of Santos Legal Services. "
            "You've been on the Starter plan for 3 months and are happy but budget-conscious. "
            "You need convincing reasons to upgrade to Shield at $997/month. "
            "Ask about the financial guarantee and HAWK Certified badge."
        ),
    },
    "product_knowledge": {
        "title": "Product Knowledge Quiz",
        "description": "Test your knowledge of Hawk Security products and features.",
        "persona": (
            "You are a senior sales trainer at Hawk Security. "
            "Ask the trainee 5 questions about Hawk products, pricing, features, "
            "PIPEDA compliance, the financial guarantee, HAWK Certified badge, "
            "and target market. Score each answer 1-10 and provide feedback. "
            "Start with the first question immediately."
        ),
    },
}


def start_training_session(
    user_id: str,
    scenario_type: str,
) -> dict[str, Any]:
    """Start a new training roleplay session."""
    if scenario_type not in SCENARIO_TYPES:
        return {"error": f"Unknown scenario: {scenario_type}", "available": list(SCENARIO_TYPES.keys())}

    scenario = SCENARIO_TYPES[scenario_type]

    session_data = {
        "user_id": user_id,
        "scenario_type": scenario_type,
        "title": scenario["title"],
        "description": scenario["description"],
        "status": "active",
        "messages": [],
        "score": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store in DB
    if SUPABASE_URL and SERVICE_KEY:
        try:
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_training_sessions",
                headers={**_sb(), "Prefer": "return=representation"},
                json=session_data,
                timeout=20.0,
            )
            if r.status_code < 400:
                rows = r.json()
                if isinstance(rows, list) and rows:
                    session_data["id"] = rows[0].get("id")
        except Exception as exc:
            logger.warning("Failed to store training session: %s", exc)

    # Generate opening message from the persona
    opening = _generate_response(scenario_type, [], "Begin the roleplay. Introduce yourself in character.")
    session_data["opening_message"] = opening

    return session_data


def training_chat(
    session_id: str,
    user_message: str,
    conversation_history: list[dict[str, str]],
    scenario_type: str,
) -> dict[str, Any]:
    """Continue a training roleplay conversation."""
    response = _generate_response(scenario_type, conversation_history, user_message)
    return {"reply": response, "session_id": session_id}


def end_training_session(
    session_id: str,
    conversation_history: list[dict[str, str]],
    scenario_type: str,
) -> dict[str, Any]:
    """End a training session and get performance feedback."""
    if not OPENAI_API_KEY:
        return {"error": "OpenAI not configured"}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

        history_text = "\n".join(
            f"{'Trainee' if m.get('role') == 'user' else 'Prospect'}: {m.get('content', '')}"
            for m in conversation_history
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior sales coach at Hawk Security. "
                        "Score the trainee's performance in this roleplay on a scale of 1-100. "
                        "Return JSON: {\"score\": 0, \"grade\": \"A/B/C/D/F\", "
                        "\"strengths\": [\"...\"], \"improvements\": [\"...\"], "
                        "\"overall_feedback\": \"...\"}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Scenario: {SCENARIO_TYPES.get(scenario_type, {}).get('title', scenario_type)}\n\n"
                        f"Conversation:\n{history_text}"
                    ),
                },
            ],
            max_tokens=800,
            temperature=0.3,
        )

        import re

        text = (response.choices[0].message.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            feedback = json.loads(m.group(0))
            # Update session in DB
            if SUPABASE_URL and SERVICE_KEY:
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/aria_training_sessions",
                    headers=_sb(),
                    params={"id": f"eq.{session_id}"},
                    json={"status": "completed", "score": feedback.get("score")},
                    timeout=15.0,
                )
            return feedback
        return {"score": 0, "overall_feedback": text}
    except Exception as exc:
        logger.exception("Training feedback failed: %s", exc)
        return {"error": str(exc)}


def _generate_response(
    scenario_type: str,
    conversation_history: list[dict[str, str]],
    user_message: str,
) -> str:
    """Generate a roleplay response from the scenario persona."""
    if not OPENAI_API_KEY:
        return "Training mode requires OpenAI API key."

    scenario = SCENARIO_TYPES.get(scenario_type, SCENARIO_TYPES["cold_call"])

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    f"{scenario['persona']}\n\n"
                    "Stay in character at all times. Keep responses natural and conversational. "
                    "Do not break character or acknowledge you are an AI."
                ),
            },
        ]

        for m in conversation_history[-20:]:
            role = m.get("role", "user")
            if role not in ("user", "assistant"):
                continue
            messages.append({"role": role, "content": m.get("content", "")})

        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )

        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("Training response generation failed: %s", exc)
        return "I'm having trouble responding right now. Let's continue in a moment."


def list_scenarios() -> list[dict[str, str]]:
    """List available training scenarios."""
    return [
        {"type": k, "title": v["title"], "description": v["description"]}
        for k, v in SCENARIO_TYPES.items()
    ]


def get_training_history(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get training session history for a user."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return []

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_training_sessions",
        headers=_sb(),
        params={
            "user_id": f"eq.{user_id}",
            "select": "id,scenario_type,title,status,score,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        },
        timeout=20.0,
    )
    return r.json() if r.status_code < 400 else []
