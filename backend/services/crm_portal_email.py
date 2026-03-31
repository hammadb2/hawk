"""Resend — client portal onboarding emails (Phase 2B)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from config import RESEND_API_KEY, RESEND_FROM_EMAIL

logger = logging.getLogger(__name__)


def send_resend(
    *,
    to_email: str,
    subject: str,
    html: str,
    tags: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """POST https://api.resend.com/emails — returns JSON or raises."""
    if not RESEND_API_KEY:
        logger.info("RESEND_API_KEY not set — skip email to %s: %s", to_email, subject)
        return {"skipped": True}

    body: dict[str, Any] = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if tags:
        body["tags"] = tags

    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json=body,
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def welcome_portal_email(*, to_email: str, company_name: str, portal_url: str) -> dict[str, Any]:
    html = f"""
    <p>Hi {company_name},</p>
    <p>Your HAWK client portal is ready. Open it anytime:</p>
    <p><a href="{portal_url}">{portal_url}</a></p>
    <p>Sign in with this email — we&apos;ll send you a secure magic link.</p>
    """
    return send_resend(
        to_email=to_email,
        subject="Welcome to your HAWK security portal",
        html=html,
        tags=[{"name": "category", "value": "portal_welcome"}],
    )
