"""HAWK Sentinel — Interactive Rules of Engagement (ROE) Chat.

Negotiates the penetration test scope with the customer via an AI legal
agent. Produces a structured scope.json contract that gates the audit.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

ROE_SYSTEM_PROMPT = """\
You are a Cybersecurity Legal & Compliance AI Agent for HAWK Sentinel, \
a premium automated penetration testing service.

Your role is to negotiate the Rules of Engagement (ROE) with the customer \
before an automated penetration test can begin. You MUST:

1. Greet the customer and explain that HAWK Sentinel will perform an \
   automated security audit of their infrastructure.
2. Ask which domains/subdomains are in scope (e.g., "*.clientdomain.com").
3. Ask if there are any IP addresses or hosts that must be EXCLUDED.
4. Ask about their risk tolerance — specifically whether active exploitation \
   (payload delivery, shell access attempts) is permitted, or if the test \
   should be limited to deep scanning and enumeration only.
5. Confirm the agreed scope back to the customer in plain language.
6. Once the customer confirms, output a JSON block wrapped in ```json fences \
   with EXACTLY this structure:

```json
{
  "roe_agreed": true,
  "exploitation_allowed": false,
  "intensity": "deep_scan_only",
  "in_scope_domains": ["*.clientdomain.com"],
  "excluded_ips": [],
  "notes": ""
}
```

Rules:
- "intensity" must be one of: "deep_scan_only", "exploit_safe", "full_exploit"
- "exploitation_allowed" must be false if intensity is "deep_scan_only"
- "exploitation_allowed" must be true if intensity is "full_exploit"
- "exploit_safe" means exploitation is allowed but no destructive payloads
- Do NOT output the JSON until the customer explicitly agrees to the scope
- Be professional, concise, and legally precise
- If the customer asks questions about the process, answer helpfully
- Always remind them this is an automated test and they can stop it at any time
"""


def _extract_scope_json(text: str) -> dict[str, Any] | None:
    """Try to extract a scope.json block from the LLM response."""
    import re
    pattern = r"```json\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("Failed to parse scope JSON from LLM response")
            return None
    return None


def _validate_scope(scope: dict[str, Any]) -> list[str]:
    """Validate the scope contract and return a list of issues."""
    issues: list[str] = []
    if not scope.get("roe_agreed"):
        issues.append("roe_agreed must be true")
    if "exploitation_allowed" not in scope:
        issues.append("exploitation_allowed field is required")
    intensity = scope.get("intensity", "")
    if intensity not in ("deep_scan_only", "exploit_safe", "full_exploit"):
        issues.append(f"Invalid intensity: {intensity}")
    if intensity == "deep_scan_only" and scope.get("exploitation_allowed"):
        issues.append("exploitation_allowed must be false for deep_scan_only")
    if intensity == "full_exploit" and not scope.get("exploitation_allowed"):
        issues.append("exploitation_allowed must be true for full_exploit")
    domains = scope.get("in_scope_domains", [])
    if not isinstance(domains, list) or len(domains) == 0:
        issues.append("At least one in_scope_domains is required")
    return issues


async def roe_chat_turn(
    chat_history: list[dict[str, str]],
    user_message: str,
    settings: Settings | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Process one turn of the ROE chat.

    Returns (assistant_reply, scope_json_or_none).
    If the AI produces a valid scope.json, it's returned as the second element.
    """
    settings = settings or get_settings()

    if not settings.sentinel_llm_api_key:
        raise RuntimeError("SENTINEL_LLM_API_KEY not configured")

    messages = [{"role": "system", "content": ROE_SYSTEM_PROMPT}]
    messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})

    async with AsyncOpenAI(
        api_key=settings.sentinel_llm_api_key,
        base_url=settings.sentinel_llm_base_url,
        timeout=60,
    ) as client:
        response = await client.chat.completions.create(
            model=settings.sentinel_llm_model,
            messages=messages,
            temperature=0.4,
            max_tokens=1500,
        )

    content = response.choices[0].message.content or ""

    scope = _extract_scope_json(content)
    if scope:
        issues = _validate_scope(scope)
        if issues:
            logger.warning("Scope validation issues: %s", issues)
            scope = None

    return content.strip(), scope
