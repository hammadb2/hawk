"""
ARIA Inbox Health Monitoring — monitors bounce rate, spam complaints, reply rate per sending domain.

Thresholds:
- 2% bounce = alert, 3% bounce = pause domain
- 0.1% spam complaint = alert, 0.3% spam = pause domain
- Weekly MXToolbox blacklist check

Runs daily via POST /api/crm/cron/inbox-health.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from config import MXTOOLBOX_API_KEY, SMARTLEAD_API_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SMARTLEAD_BASE = os.environ.get("SMARTLEAD_API_BASE", "https://server.smartlead.ai/api/v1").rstrip("/")
MXTOOLBOX_BASE = "https://mxtoolbox.com/api/v1"

# Alert thresholds
BOUNCE_ALERT_PCT = 0.02    # 2%
BOUNCE_PAUSE_PCT = 0.03    # 3%
SPAM_ALERT_PCT = 0.001     # 0.1%
SPAM_PAUSE_PCT = 0.003     # 0.3%


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# ── Smartlead Stats Fetching ────────────────────────────────────────────

def _fetch_smartlead_email_accounts() -> list[dict[str, Any]]:
    """Fetch all email accounts from Smartlead."""
    if not SMARTLEAD_API_KEY:
        return []

    try:
        r = httpx.get(
            f"{SMARTLEAD_BASE}/email-accounts",
            params={"api_key": SMARTLEAD_API_KEY},
            timeout=30.0,
        )
        if r.status_code >= 400:
            logger.warning("Smartlead email accounts fetch failed: %s", r.text[:300])
            return []
        return r.json() or []
    except Exception as exc:
        logger.warning("Failed to fetch Smartlead email accounts: %s", exc)
        return []


def _fetch_smartlead_campaign_stats(campaign_id: str) -> dict[str, Any]:
    """Fetch campaign statistics from Smartlead."""
    if not SMARTLEAD_API_KEY:
        return {}

    try:
        r = httpx.get(
            f"{SMARTLEAD_BASE}/campaigns/{campaign_id}/analytics",
            params={"api_key": SMARTLEAD_API_KEY},
            timeout=30.0,
        )
        if r.status_code >= 400:
            return {}
        return r.json() or {}
    except Exception as exc:
        logger.warning("Campaign stats fetch failed for %s: %s", campaign_id, exc)
        return {}


def _aggregate_domain_stats() -> dict[str, dict[str, int]]:
    """
    Aggregate email stats per sending domain from Smartlead.
    Returns dict of domain → {sent, bounces, spam_complaints, replies}.
    """
    domain_stats: dict[str, dict[str, int]] = {}

    # Get all email accounts
    accounts = _fetch_smartlead_email_accounts()
    for account in accounts:
        email = account.get("from_email") or ""
        if "@" not in email:
            continue

        domain = email.split("@")[-1].lower()
        if domain not in domain_stats:
            domain_stats[domain] = {
                "emails_sent_total": 0,
                "emails_sent_7d": 0,
                "bounces_7d": 0,
                "spam_complaints_7d": 0,
                "replies_7d": 0,
            }

        # Smartlead account-level stats
        stats = account.get("stats") or {}
        domain_stats[domain]["emails_sent_total"] += int(stats.get("total_sent") or 0)
        domain_stats[domain]["emails_sent_7d"] += int(stats.get("sent_last_7_days") or 0)
        domain_stats[domain]["bounces_7d"] += int(stats.get("bounced_last_7_days") or 0)
        domain_stats[domain]["spam_complaints_7d"] += int(stats.get("spam_last_7_days") or 0)
        domain_stats[domain]["replies_7d"] += int(stats.get("replied_last_7_days") or 0)

    return domain_stats


# ── MXToolbox Blacklist Check ───────────────────────────────────────────

def _check_mxtoolbox_blacklist(domain: str) -> dict[str, Any]:
    """Check a domain against MXToolbox blacklist database."""
    if not MXTOOLBOX_API_KEY:
        return {"checked": False, "reason": "MXTOOLBOX_API_KEY not configured"}

    try:
        r = httpx.get(
            f"{MXTOOLBOX_BASE}/lookup/blacklist/{domain}",
            headers={"Authorization": MXTOOLBOX_API_KEY},
            timeout=30.0,
        )
        if r.status_code >= 400:
            return {"checked": False, "reason": f"API error: {r.status_code}"}

        data = r.json()
        failed = data.get("Failed") or []
        blacklisted = len(failed) > 0
        entries = [
            {
                "blacklist": f.get("Name", ""),
                "info": f.get("Info", ""),
            }
            for f in failed
        ]

        return {
            "checked": True,
            "blacklisted": blacklisted,
            "entries": entries,
            "total_checked": data.get("TotalChecks", 0),
            "failed_count": len(failed),
        }
    except Exception as exc:
        logger.warning("MXToolbox check failed for %s: %s", domain, exc)
        return {"checked": False, "reason": str(exc)[:300]}


# ── Health Assessment ───────────────────────────────────────────────────

def _assess_domain_health(stats: dict[str, int]) -> dict[str, Any]:
    """Assess health status for a domain based on stats."""
    sent = stats.get("emails_sent_7d", 0) or 1  # avoid division by zero
    bounces = stats.get("bounces_7d", 0)
    spam = stats.get("spam_complaints_7d", 0)
    replies = stats.get("replies_7d", 0)

    bounce_rate = bounces / sent if sent else 0
    spam_rate = spam / sent if sent else 0
    reply_rate = replies / sent if sent else 0

    alerts: list[str] = []
    status = "healthy"

    # Bounce rate assessment
    if bounce_rate >= BOUNCE_PAUSE_PCT:
        status = "paused"
        alerts.append(f"CRITICAL: bounce rate {bounce_rate:.1%} exceeds {BOUNCE_PAUSE_PCT:.0%} threshold — domain paused")
    elif bounce_rate >= BOUNCE_ALERT_PCT:
        status = "warning"
        alerts.append(f"WARNING: bounce rate {bounce_rate:.1%} exceeds {BOUNCE_ALERT_PCT:.0%} threshold")

    # Spam rate assessment
    if spam_rate >= SPAM_PAUSE_PCT:
        status = "paused"
        alerts.append(f"CRITICAL: spam rate {spam_rate:.2%} exceeds {SPAM_PAUSE_PCT:.1%} threshold — domain paused")
    elif spam_rate >= SPAM_ALERT_PCT:
        if status != "paused":
            status = "warning"
        alerts.append(f"WARNING: spam rate {spam_rate:.2%} exceeds {SPAM_ALERT_PCT:.1%} threshold")

    return {
        "bounce_rate_7d": round(bounce_rate, 4),
        "spam_rate_7d": round(spam_rate, 4),
        "reply_rate_7d": round(reply_rate, 4),
        "health_status": status,
        "alerts": alerts,
    }


# ── Database Operations ─────────────────────────────────────────────────

def _upsert_domain_health(domain: str, data: dict[str, Any]) -> None:
    """Upsert domain health record in aria_domain_health."""
    if not SUPABASE_URL:
        return

    headers = _sb_headers()
    now = datetime.now(timezone.utc).isoformat()

    row = {
        "domain": domain,
        "emails_sent_total": data.get("emails_sent_total", 0),
        "emails_sent_7d": data.get("emails_sent_7d", 0),
        "bounces_7d": data.get("bounces_7d", 0),
        "spam_complaints_7d": data.get("spam_complaints_7d", 0),
        "replies_7d": data.get("replies_7d", 0),
        "bounce_rate_7d": data.get("bounce_rate_7d", 0),
        "spam_rate_7d": data.get("spam_rate_7d", 0),
        "reply_rate_7d": data.get("reply_rate_7d", 0),
        "health_status": data.get("health_status", "healthy"),
        "updated_at": now,
    }

    if data.get("health_status") == "paused":
        row["paused_at"] = now
        row["pause_reason"] = "; ".join(data.get("alerts", []))

    if data.get("blacklist_data"):
        bl = data["blacklist_data"]
        row["blacklisted"] = bl.get("blacklisted", False)
        row["blacklist_entries"] = json.dumps(bl.get("entries", []))
        row["last_blacklist_check"] = now

    # Check if exists
    try:
        chk = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_domain_health",
            headers=headers,
            params={"domain": f"eq.{domain}", "select": "id", "limit": "1"},
            timeout=15.0,
        )
        chk.raise_for_status()
        if chk.json():
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/aria_domain_health",
                headers=headers,
                params={"domain": f"eq.{domain}"},
                json=row,
                timeout=15.0,
            ).raise_for_status()
        else:
            row["created_at"] = now
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_domain_health",
                headers=headers,
                json=row,
                timeout=15.0,
            ).raise_for_status()
    except Exception as exc:
        logger.warning("Failed to upsert domain health for %s: %s", domain, exc)


def _create_health_alert(domain: str, alerts: list[str], status: str) -> None:
    """Create a CRM notification for health alerts."""
    if not SUPABASE_URL or not alerts:
        return

    headers = _sb_headers()
    alert_text = f"Inbox health alert for {domain}: {'; '.join(alerts)}"

    try:
        # Notify CEO
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_notifications",
            headers=headers,
            json={
                "recipient_role": "ceo",
                "title": f"Inbox Health {'CRITICAL' if status == 'paused' else 'Warning'}: {domain}",
                "body": alert_text,
                "category": "inbox_health",
                "read": False,
            },
            timeout=15.0,
        )
    except Exception:
        logger.warning("Failed to create health alert notification for %s", domain)


# ── Inbox Health Orchestrator ───────────────────────────────────────────

def run_inbox_health_check(include_blacklist: bool = False) -> dict[str, Any]:
    """
    Run inbox health monitoring:
    1. Fetch email stats per domain from Smartlead
    2. Assess bounce/spam rates against thresholds
    3. Optional: run MXToolbox blacklist check (weekly)
    4. Update aria_domain_health table
    5. Create alerts for warning/paused domains

    Returns summary.
    """
    stats: dict[str, Any] = {
        "ok": True,
        "domains_checked": 0,
        "healthy": 0,
        "warning": 0,
        "paused": 0,
        "alerts": [],
    }

    try:
        # Get domain-level stats from Smartlead
        domain_stats = _aggregate_domain_stats()
        stats["domains_checked"] = len(domain_stats)

        for domain, d_stats in domain_stats.items():
            assessment = _assess_domain_health(d_stats)

            # Merge stats + assessment
            health_data = {**d_stats, **assessment}

            # Optional blacklist check
            if include_blacklist:
                bl = _check_mxtoolbox_blacklist(domain)
                health_data["blacklist_data"] = bl
                if bl.get("blacklisted"):
                    assessment["alerts"].append(f"Domain {domain} is blacklisted on {bl.get('failed_count', 0)} lists")
                    if assessment["health_status"] != "paused":
                        assessment["health_status"] = "warning"
                    health_data["health_status"] = assessment["health_status"]

            # Store in DB
            _upsert_domain_health(domain, health_data)

            # Count statuses
            status = assessment["health_status"]
            if status == "healthy":
                stats["healthy"] += 1
            elif status == "warning":
                stats["warning"] += 1
                _create_health_alert(domain, assessment["alerts"], status)
                stats["alerts"].extend([f"{domain}: {a}" for a in assessment["alerts"]])
            elif status == "paused":
                stats["paused"] += 1
                _create_health_alert(domain, assessment["alerts"], status)
                stats["alerts"].extend([f"{domain}: {a}" for a in assessment["alerts"]])

        # Send CEO SMS if any domains are paused
        if stats["paused"] > 0:
            _send_health_alert_sms(stats)

    except Exception as exc:
        logger.exception("Inbox health check failed: %s", exc)
        stats["ok"] = False
        stats["error"] = str(exc)[:1000]

    logger.info("Inbox health check complete: %s", json.dumps({k: v for k, v in stats.items() if k != "alerts"}))
    return stats


def _send_health_alert_sms(stats: dict[str, Any]) -> None:
    """Send CEO SMS when domains are paused."""
    try:
        from services.crm_openphone import send_ceo_sms

        msg = (
            f"ARIA inbox health alert: {stats['paused']} domain(s) paused, "
            f"{stats['warning']} warning(s).\n"
            + "\n".join(stats.get("alerts", [])[:5])
        )
        send_ceo_sms(msg[:1500])
    except Exception:
        logger.exception("Health alert SMS failed")
