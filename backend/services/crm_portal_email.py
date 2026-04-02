"""Resend — client portal onboarding emails (Phase 2B)."""

from __future__ import annotations

import html as html_module
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


def shield_day0_welcome_email(
    *,
    to_email: str,
    company_name: str,
    portal_url: str,
    booking_url: str,
) -> dict[str, Any]:
    """HAWK Shield — Day 0 welcome after payment (Resend)."""
    html = f"""
    <p>Hi {company_name},</p>
    <p>Welcome to <strong>HAWK Shield</strong>. Your breach response guarantee is now active, and your 90-day path to <strong>HAWK Certified</strong> starts today.</p>
    <p><strong>Your portal</strong> — sign in with this email for magic links:<br/>
    <a href="{portal_url}">{portal_url}</a></p>
    <p><strong>Onboarding call</strong> — book a walkthrough of your findings and fix plan:<br/>
    <a href="{booking_url}">{booking_url}</a></p>
    <p><strong>Guarantee summary</strong></p>
    <ul>
      <li>Coverage: incident response costs for a confirmed security breach, up to your plan limits, when conditions are met.</li>
      <li>Critical findings must be resolved within 24–48 hours of notification; high findings within 48 hours.</li>
      <li>Subscription must stay active; HAWK recommendations followed within stated timeframes.</li>
      <li>Not covered: employee error, systems we don&apos;t monitor, vendor breaches, pre-existing compromises, unreported incidents.</li>
    </ul>
    <p>Questions: <a href="mailto:hello@akbstudios.com">hello@akbstudios.com</a></p>
    """
    return send_resend(
        to_email=to_email,
        subject=f"Welcome to HAWK Shield — {company_name}",
        html=html,
        tags=[{"name": "category", "value": "shield_day0_welcome"}],
    )


def shield_day1_findings_email(
    *,
    to_email: str,
    company_name: str,
    portal_url: str,
    booking_url: str,
    top_findings: list[tuple[str, str]],
) -> dict[str, Any]:
    """Day 1 — top 3 findings in plain English + CTA to portal."""
    esc = html_module.escape
    items = ""
    for title, plain in top_findings[:3]:
        items += f"<li><strong>{esc(title)}</strong> — {esc(plain)}</li>"
    if not items:
        items = "<li>Log in to your portal for your full report and prioritized list.</li>"
    html = f"""
    <p>Hi {esc(company_name)},</p>
    <p>Here is a plain-English summary of your <strong>top findings</strong> and what to do next. Full fix guides live in your portal.</p>
    <ol>{items}</ol>
    <p><a href="{esc(portal_url)}">Open your HAWK portal</a> — step-by-step fix guides and verification.</p>
    <p>Book your onboarding call to walk through the plan: <a href="{esc(booking_url)}">{esc(booking_url)}</a></p>
    <p style="color:#666;font-size:12px">HAWK Shield</p>
    """
    return send_resend(
        to_email=to_email,
        subject=f"Your HAWK findings — {company_name}",
        html=html,
        tags=[{"name": "category", "value": "shield_day1_findings"}],
    )


def shield_day7_week_summary_email(
    *,
    to_email: str,
    company_name: str,
    portal_url: str,
    score_now: int,
    score_was: int,
    findings_fixed: int,
    findings_remaining: int,
    days_until_certified: int,
    progress_pct: int,
) -> dict[str, Any]:
    """Day 7 — week one summary with certification progress bar."""
    esc = html_module.escape
    pct = max(0, min(100, progress_pct))
    html = f"""
    <p>Hi {esc(company_name)},</p>
    <p><strong>HAWK Week One Summary</strong></p>
    <ul>
      <li>Score now: <strong>{score_now}/100</strong> (was <strong>{score_was}/100</strong> at signup)</li>
      <li>Findings addressed this week: <strong>{findings_fixed}</strong></li>
      <li>Findings still open: <strong>{findings_remaining}</strong></li>
      <li>What we did: daily Shield monitoring and scanning on your domain; alerts when new critical/high risks appear.</li>
      <li>Days until HAWK Certified eligibility: <strong>{days_until_certified}</strong> (90-day track from onboarding)</li>
    </ul>
    <p>Certification progress</p>
    <div style="background:#e5e7eb;border-radius:8px;height:24px;max-width:400px;overflow:hidden">
      <div style="background:#16a34a;height:100%;width:{pct}%;min-width:0"></div>
    </div>
    <p style="font-size:12px;color:#666">{pct}% of the 90-day certification window</p>
    <p><a href="{esc(portal_url)}">Open your HAWK portal</a></p>
    <p style="color:#666;font-size:12px">HAWK Shield</p>
    """
    return send_resend(
        to_email=to_email,
        subject=f"HAWK Week One — {company_name}",
        html=html,
        tags=[{"name": "category", "value": "shield_day7_summary"}],
    )
