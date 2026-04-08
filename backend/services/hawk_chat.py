"""Ask HAWK — DeepSeek R1 with scan context in system prompt."""
from __future__ import annotations

import json
import re

import httpx

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_REASONER_MODEL,
    PLAN_ASK_HAWK_LIMIT,
)


def build_system_prompt(
    findings_json: str | None,
    score: int | None,
    grade: str | None,
    domain: str,
    industry: str | None,
    province: str | None,
    plan: str,
) -> str:
    parts = [
        "You are Ask HAWK, a cybersecurity advisor for Canadian SMBs. "
        "You talk like a knowledgeable friend — direct, clear, and human. "
        "Keep replies short and focused. No walls of text. No unnecessary headers or bullet soup. "
        "If the question is simple, give a simple answer (2-4 sentences). "
        "Only use bullet points or headers when there are genuinely multiple distinct steps. "
        "Map findings to PIPEDA and Bill C-26 only when directly relevant. "
        "Never start with a preamble like 'Great question!' or 'Sure!'. Just answer.",
        f"User's domain: {domain}. Current scan grade: {grade or 'N/A'} (score: {score or 0}/100). Plan: {plan}.",
    ]
    if industry:
        parts.append(f"Industry: {industry}.")
    if province:
        parts.append(f"Province: {province}.")
    if findings_json:
        try:
            findings = json.loads(findings_json)
            parts.append("Current scan findings (use these to give specific advice):")
            for f in findings[:50]:
                parts.append(f"  - [{f.get('severity')}] {f.get('title')}: {f.get('description')}")
        except Exception:
            parts.append("(Findings could not be loaded.)")
    parts.append(
        "If the user has fixed something and wants to rescan a specific check, end your reply with [TRIGGER_RESCAN:check_name] where check_name is the category (e.g. DNS, SSL, Web)."
    )
    return "\n".join(parts)


def extract_trigger_rescan(reply: str) -> str | None:
    m = re.search(r"\[TRIGGER_RESCAN:(\w+)\]", reply)
    return m.group(1) if m else None


def chat(
    message: str,
    system_prompt: str,
    conversation_history: list[dict],
) -> tuple[str, str | None]:
    """
    Call DeepSeek R1. Returns (reply_text, trigger_rescan_check_name or None).
    """
    if not DEEPSEEK_API_KEY:
        return "Ask HAWK is not configured (missing API key).", None
    messages = [{"role": "system", "content": system_prompt}]
    for h in conversation_history[-10:]:
        role = h.get("role", "user")
        content = h.get("content", h.get("message", ""))
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/v1/chat/completions"
    with httpx.Client(timeout=60) as client:
        r = client.post(
            url,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": DEEPSEEK_REASONER_MODEL,
                "messages": messages,
            },
        )
        r.raise_for_status()
        data = r.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")
    trigger = extract_trigger_rescan(content)
    if trigger:
        content = re.sub(r"\s*\[TRIGGER_RESCAN:\w+\]\s*$", "", content).strip()
    return content, trigger
