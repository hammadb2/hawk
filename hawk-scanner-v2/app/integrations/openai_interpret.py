"""OpenAI — turn raw findings into plain English + fix guides (batch)."""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def interpret_findings(findings: list[dict[str, Any]], settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        return []
    client = AsyncOpenAI(api_key=settings.openai_api_key)
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
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=8000,
            messages=[
                {"role": "user", "content": prompt + "\n\nFINDINGS:\n" + json.dumps(slim, indent=2)},
            ],
        )
    except Exception as e:
        logger.exception("openai interpret failed: %s", e)
        return []
    text = (completion.choices[0].message.content or "").strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        items = data.get("items") or []
        return [dict(x) for x in items if isinstance(x, dict)]
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("openai JSON parse failed: %s", e)
        return []
