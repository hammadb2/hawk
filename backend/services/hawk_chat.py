"""Ask HAWK — OpenAI with scan context in system prompt."""
from __future__ import annotations

import json
import os
import re

from config import OPENAI_API_KEY, OPENAI_MODEL
from services.openai_chat import chat_text_sync


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
        "You are Ask HAWK, a cybersecurity advisor for US small professional practices (dental, legal, accounting / CPA). "
        "You talk like a knowledgeable friend — direct, clear, and human. "
        "Keep replies short and focused. No walls of text. No unnecessary headers or bullet soup. "
        "If the question is simple, give a simple answer (2-4 sentences). "
        "Only use bullet points or headers when there are genuinely multiple distinct steps. "
        "Map findings to the US regulatory angle appropriate to the vertical: HIPAA Security Rule (dental / medical), FTC Safeguards Rule (CPA / tax), ABA Formal Opinion 24-514 (legal). Only reference them when directly relevant. "
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
    Call OpenAI Chat Completions. Returns (reply_text, trigger_rescan_check_name or None).
    """
    if not OPENAI_API_KEY:
        return "Ask HAWK is not configured (missing OPENAI_API_KEY).", None
    ask_model = (os.environ.get("HAWK_ASK_OPENAI_MODEL") or "").strip() or OPENAI_MODEL
    user_messages: list[dict[str, str]] = []
    for h in conversation_history[-10:]:
        role = h.get("role", "user")
        content = h.get("content", h.get("message", ""))
        if role in ("user", "assistant"):
            user_messages.append({"role": role, "content": str(content)})
    user_messages.append({"role": "user", "content": message})
    content = chat_text_sync(
        api_key=OPENAI_API_KEY,
        system=system_prompt,
        user_messages=user_messages,
        max_tokens=4096,
        model=ask_model,
    )
    trigger = extract_trigger_rescan(content)
    if trigger:
        content = re.sub(r"\s*\[TRIGGER_RESCAN:\w+\]\s*$", "", content).strip()
    return content, trigger
