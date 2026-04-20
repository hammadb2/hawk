"""Transactional email helpers (welcome, password reset, critical findings, digests).

These are app-triggered one-off emails (not campaign sends). The project doesn't
ship an SMTP sender by default, so every helper here no-ops cleanly and returns
False if no delivery backend is wired up.

To actually deliver mail, set ``TRANSACTIONAL_EMAIL_WEBHOOK_URL`` (and optionally
``TRANSACTIONAL_EMAIL_API_KEY``) in the environment — the payload is POSTed as
``{"task": "send_email", "to": ..., "subject": ..., "body": ...}`` so any simple
relay (Resend proxy, Postmark webhook shim, a Cloudflare Worker, etc.) can accept
it without us hard-coding a provider.
"""

from __future__ import annotations

import os

import httpx

from config import BASE_URL

_WEBHOOK_URL = os.environ.get("TRANSACTIONAL_EMAIL_WEBHOOK_URL", "").strip()
_WEBHOOK_KEY = os.environ.get("TRANSACTIONAL_EMAIL_API_KEY", "").strip()


def send_email(to: str, subject: str, body: str) -> bool:
    """POST to a transactional-email relay if configured; otherwise return False.

    Intentionally silent on failure — callers treat delivery as best-effort.
    """
    if not _WEBHOOK_URL:
        return False
    headers = {"Content-Type": "application/json"}
    if _WEBHOOK_KEY:
        headers["X-API-Key"] = _WEBHOOK_KEY
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(
                _WEBHOOK_URL,
                headers=headers,
                json={"task": "send_email", "to": to, "subject": subject, "body": body},
            )
            return r.is_success
    except Exception:
        return False


def welcome_email(to: str, first_name: str | None = None) -> bool:
    name = (first_name or "there").strip() or "there"
    subject = "Welcome to HAWK"
    body = f"""Hi {name},

Welcome to HAWK.

Next steps:
• Add your domain in the dashboard
• Run a scan to see your external attack surface
• Check Findings and use Ask HAWK for fix guidance

Log in at {BASE_URL}/login

— The HAWK team
"""
    return send_email(to, subject, body)


def critical_finding_alert(
    to: str,
    domain: str,
    scan_id: str,
    critical_count: int,
    titles: list[str] | None = None,
) -> bool:
    subject = f"HAWK: {critical_count} critical finding(s) for {domain}"
    lines = [
        f"We found {critical_count} critical finding(s) on {domain}.",
        "",
        "View details:",
        f"{BASE_URL}/dashboard/findings?scan={scan_id}",
        "",
    ]
    if titles:
        lines.append("Findings:")
        for t in titles[:10]:
            lines.append(f"  • {t}")
    return send_email(to, subject, "\n".join(lines))


def weekly_digest_email(
    to: str,
    scan_count: int,
    critical_total: int,
    domains: list[str],
    first_name: str | None = None,
) -> bool:
    name = (first_name or "there").strip() or "there"
    subject = "HAWK: Your weekly security digest"
    body = f"""Hi {name},

Your weekly HAWK digest for the past 7 days:

  Scans run: {scan_count}
  Critical findings (total): {critical_total}
  Domains: {", ".join(domains[:10]) or "—"}

View your dashboard: {BASE_URL}/dashboard

— The HAWK team
"""
    return send_email(to, subject, body)


def password_reset_email(to: str, reset_url: str, first_name: str | None = None) -> bool:
    name = (first_name or "there").strip() or "there"
    subject = "HAWK: Reset your password"
    body = f"""Hi {name},

You requested a password reset. Click the link below to set a new password (valid for 1 hour):

{reset_url}

If you didn't request this, you can ignore this email.

— The HAWK team
"""
    return send_email(to, subject, body)


def monthly_report_ready_email(to: str, first_name: str | None = None) -> bool:
    name = (first_name or "there").strip() or "there"
    subject = "HAWK: Your monthly report is ready"
    body = f"""Hi {name},

Your monthly security report is ready to view and download.

Dashboard: {BASE_URL}/dashboard/reports

— The HAWK team
"""
    return send_email(to, subject, body)


def trial_expiry_tomorrow_email(_to: str, _first_name: str | None = None) -> bool:
    """Product trials are not offered; cron endpoint is a no-op."""
    return False
