"""OpenAI — top 3 attack paths from findings (2B)."""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def compute_attack_paths(
    *,
    domain: str,
    industry: str | None,
    company_name: str | None,
    findings: list[dict[str, Any]],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        return []

    slim = [
        {
            "id": f.get("id"),
            "severity": f.get("severity"),
            "title": f.get("title"),
            "description": (f.get("description") or "")[:900],
            "layer": f.get("layer"),
            "affected_asset": (f.get("affected_asset") or "")[:300],
        }
        for f in findings[:35]
    ]
    org = (company_name or domain or "this organization").strip()
    ind = (industry or "small business").strip()

    prompt = (
        f"You are a penetration tester analyzing a {ind} business called {org} in Canada. "
        f"Their domain is {domain}. Their security findings are:\n"
        f"{json.dumps(slim, indent=2)}\n\n"
        "Describe the top 3 attack paths an attacker would use to breach this business. "
        "For each path: give a short name, list exact steps numbered (1. 2. 3.), "
        "rate likelihood as exactly High, Medium, or Low, and describe business impact in plain English "
        f"for a {ind} owner. No technical jargon. "
        'Output ONLY valid JSON: {"paths":[{"name":"...","steps":["1. ...","2. ..."],"likelihood":"High|Medium|Low","impact":"..."}]}'
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.exception("attack_paths openai failed: %s", e)
        return []

    text = (completion.choices[0].message.content or "").strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        paths = data.get("paths") or []
        out: list[dict[str, Any]] = []
        for p in paths[:3]:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "Attack path")
            steps = p.get("steps")
            if not isinstance(steps, list):
                steps = [str(steps)] if steps else []
            steps = [str(s) for s in steps if s][:12]
            lik = str(p.get("likelihood") or "Medium")
            if lik not in ("High", "Medium", "Low"):
                lik = "Medium"
            impact = str(p.get("impact") or "")
            out.append({"name": name, "steps": steps, "likelihood": lik, "impact": impact})
        return out
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("attack_paths JSON parse failed: %s", e)
        return []
