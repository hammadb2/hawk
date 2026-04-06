"""Trigger Charlotte (Revenue-Ops) for transactional emails."""
from __future__ import annotations

import httpx

from config import BASE_URL, CHARLOTTE_URL, CHARLOTTE_API_KEY


def send_email(to: str, subject: str, body: str) -> bool:
    """POST to Charlotte agent. Returns True if sent, False on error (non-blocking)."""
    if not CHARLOTTE_URL or not CHARLOTTE_API_KEY:
        return False
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(
                CHARLOTTE_URL,
                headers={"X-API-Key": CHARLOTTE_API_KEY, "Content-Type": "application/json"},
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
    lines = [f"We found {critical_count} critical finding(s) on {domain}.", "", "View details:", f"{BASE_URL}/dashboard/findings?scan={scan_id}", ""]
    if titles:
        lines.append("Findings:")
        for t in titles[:10]:
            lines.append(f"  • {t}")
    body = "\n".join(lines)
    return send_email(to, subject, body)


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
