"""Claude — turn raw findings into plain English + fix guides (batch)."""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def interpret_findings(findings: list[dict[str, Any]], settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        return []
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    slim = [
        {
            "id": f.get("id"),
            "severity": f.get("severity"),
            "title": f.get("title"),
            "description": (f.get("description") or "")[:1200],
            "remediation": (f.get("remediation") or "")[:800],
            "layer": f.get("layer"),
        }
        for f in findings[:40]
    ]
    prompt = (
        "You are a security advisor for SMBs. For each finding JSON object, produce a short plain-English "
        "summary and a numbered fix guide (2–5 steps). Output ONLY valid JSON: "
        '{"items":[{"id":"<same id>","plain_english":"<string>","fix_guide":"<string>"}]}'
    )
    try:
        msg = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=8000,
            messages=[
                {"role": "user", "content": prompt + "\n\nFINDINGS:\n" + json.dumps(slim, indent=2)},
            ],
        )
    except Exception as e:
        logger.exception("claude interpret failed: %s", e)
        return []
    text = ""
    for block in msg.content:
        if block.type == "text":
            text += block.text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        items = data.get("items") or []
        return [dict(x) for x in items if isinstance(x, dict)]
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("claude JSON parse failed: %s", e)
        return []
