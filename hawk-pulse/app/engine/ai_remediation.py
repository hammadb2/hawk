"""HAWK Guard — AI Remediation Engine.

Generates tailored, copy-paste fix guides for vulnerabilities using the
asset's detected tech stack as context.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an elite Cybersecurity Incident Responder.\n"
    "Asset Tech Stack: {tech_stack}\n"
    "Vulnerability: {vulnerability}\n"
    "Task: Write a step-by-step, highly technical remediation guide to patch "
    "this vulnerability. Include exact terminal commands, configuration file "
    "changes, or code snippets required tailored specifically to their tech "
    "stack. Format the response in clean Markdown. Do not include "
    "introductory fluff."
)

SEVERITIES_FOR_REMEDIATION = frozenset({"critical", "high", "warning"})


def _extract_tech_stack(alert_detail: dict[str, Any], asset_metadata: dict[str, Any] | None) -> str:
    """Build a tech-stack string from httpx fingerprint data on the asset."""
    parts: list[str] = []
    meta = asset_metadata or {}

    tech = meta.get("tech")
    if isinstance(tech, list):
        parts.extend(str(t) for t in tech if t)
    elif isinstance(tech, str) and tech:
        parts.append(tech)

    webserver = meta.get("webserver")
    if webserver:
        parts.append(f"Web server: {webserver}")

    title = meta.get("title")
    if title:
        parts.append(f"Page title: {title}")

    host = alert_detail.get("host") or meta.get("host") or ""
    port = alert_detail.get("port") or meta.get("port") or ""
    url = alert_detail.get("url") or meta.get("url") or ""

    if host:
        parts.append(f"Host: {host}")
    if port:
        parts.append(f"Port: {port}")
    if url:
        parts.append(f"URL: {url}")

    return "; ".join(parts) if parts else "Unknown (no fingerprint data available)"


def _build_vulnerability_description(
    alert_type: str,
    severity: str,
    title: str,
    detail: dict[str, Any],
) -> str:
    """Build a concise vulnerability description from alert fields."""
    lines = [f"Type: {alert_type}", f"Severity: {severity}", f"Finding: {title}"]

    host = detail.get("host")
    port = detail.get("port")
    if host and port:
        lines.append(f"Exposed endpoint: {host}:{port}")

    url = detail.get("url")
    if url:
        lines.append(f"URL: {url}")

    subdomain = detail.get("subdomain")
    if subdomain:
        lines.append(f"Subdomain: {subdomain}")

    old_status = detail.get("old_status")
    new_status = detail.get("new_status")
    if old_status is not None and new_status is not None:
        lines.append(f"Status change: {old_status} -> {new_status}")

    return "\n".join(lines)


async def generate_remediation(
    alert_type: str,
    severity: str,
    title: str,
    detail: dict[str, Any],
    asset_metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> str:
    """
    Call the LLM to generate a Markdown remediation guide.
    Returns the Markdown string, or an error message on failure.
    """
    settings = settings or get_settings()

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping remediation generation")
        return "_Remediation guide unavailable: API key not configured._"

    tech_stack = _extract_tech_stack(detail, asset_metadata)
    vulnerability = _build_vulnerability_description(alert_type, severity, title, detail)

    system_message = SYSTEM_PROMPT.format(
        tech_stack=tech_stack,
        vulnerability=vulnerability,
    )

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.remediation_timeout_sec,
    )

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": (
                    f"Generate a remediation guide for this vulnerability:\n\n"
                    f"**{title}**\n\n"
                    f"Tech stack: {tech_stack}\n\n"
                    f"Details:\n{vulnerability}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=2000,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned empty response")
    return content.strip()


def should_generate_remediation(severity: str) -> bool:
    """Only generate remediation for critical/high/warning alerts."""
    return severity.lower().strip() in SEVERITIES_FOR_REMEDIATION
