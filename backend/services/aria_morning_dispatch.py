"""
ARIA Morning Dispatch — legacy Smartlead bulk-upload entrypoint.

Deprecated after migration to the mailbox-native SMTP dispatcher (see
``aria_rolling_dispatch``). ``run_morning_dispatch`` is kept as a thin
delegator that invokes the rolling dispatcher so any existing scheduler or
cron hook that still calls it won't break and still drives real sends.

The Smartlead helpers (``_bulk_upload_to_smartlead``, ``_ensure_campaign``,
``_ensure_campaign_sequence``) remain importable for the ``aria_prospect_pipeline``
sync hook but are no longer on the outbound hot path.
"""

from __future__ import annotations

import json
import logging
import os
import zoneinfo
from datetime import datetime, timezone
from typing import Any

import httpx

from config import SMARTLEAD_API_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

MST = zoneinfo.ZoneInfo("America/Edmonton")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SMARTLEAD_BASE = os.environ.get("SMARTLEAD_API_BASE", "https://server.smartlead.ai/api/v1").rstrip("/")

# Smartlead bulk upload limit per request
SMARTLEAD_BULK_LIMIT = 100


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get_setting(key: str, default: str = "") -> str:
    if not SUPABASE_URL:
        return default
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}", "select": "value", "limit": "1"},
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return str(rows[0].get("value") or default)
    except Exception as exc:
        logger.warning("Failed to read setting %s: %s", key, exc)
    return default


def _set_setting(key: str, value: str) -> None:
    if not SUPABASE_URL:
        return
    try:
        chk = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}", "select": "key", "limit": "1"},
            timeout=15.0,
        )
        chk.raise_for_status()
        if chk.json():
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/crm_settings",
                headers=_sb_headers(),
                params={"key": f"eq.{key}"},
                json={"value": value},
                timeout=15.0,
            ).raise_for_status()
        else:
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/crm_settings",
                headers=_sb_headers(),
                json={"key": key, "value": value},
                timeout=15.0,
            ).raise_for_status()
    except Exception as exc:
        logger.warning("Failed to write setting %s: %s", key, exc)


# ── Smartlead Campaign Management ───────────────────────────────────────

def _create_smartlead_campaign(name: str) -> str | None:
    """Create a new Smartlead campaign and return its ID."""
    if not SMARTLEAD_API_KEY:
        logger.error("SMARTLEAD_API_KEY not configured")
        return None

    try:
        r = httpx.post(
            f"{SMARTLEAD_BASE}/campaigns/create",
            params={"api_key": SMARTLEAD_API_KEY},
            json={"name": name},
            timeout=30.0,
        )
        if r.status_code >= 400:
            logger.error("Smartlead campaign create failed: %s", r.text[:500])
            return None
        data = r.json()
        return str(data.get("id") or "")
    except Exception as exc:
        logger.exception("Failed to create Smartlead campaign: %s", exc)
        return None


def _ensure_campaign(vertical: str) -> str:
    """Get or create the Smartlead campaign for a vertical."""
    setting_key = f"smartlead_campaign_id_{vertical}"
    campaign_id = _get_setting(setting_key)

    if campaign_id:
        return campaign_id

    # Create new campaign
    campaign_name = {
        "dental": "Dental Clinics Canada",
        "legal": "Law Firms Canada",
        "accounting": "Accounting Practices Canada",
    }.get(vertical, f"{vertical.title()} Canada")

    new_id = _create_smartlead_campaign(campaign_name)
    if new_id:
        _set_setting(setting_key, new_id)
        logger.info("Created Smartlead campaign for %s: %s", vertical, new_id)
        return new_id

    logger.error("Failed to create/get campaign for vertical=%s", vertical)
    return ""


# ── Smartlead Bulk Upload ───────────────────────────────────────────────

def _smartlead_lead_payload(lead: dict[str, Any]) -> dict[str, Any]:
    """Convert an inventory lead to Smartlead lead payload."""
    first_name = ""
    last_name = ""
    if lead.get("contact_name"):
        parts = lead["contact_name"].split(None, 1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""

    payload: dict[str, Any] = {
        "email": lead.get("contact_email", ""),
        "first_name": first_name,
        "last_name": last_name,
        "company_name": lead.get("business_name", ""),
        "website": lead.get("domain", ""),
        "custom_fields": {
            "domain": lead.get("domain", ""),
            "vertical": lead.get("vertical", ""),
            "city": lead.get("city", ""),
            "province": lead.get("province", ""),
            "hawk_score": str(lead.get("hawk_score") or ""),
            "vulnerability": (lead.get("vulnerability_found") or "")[:200],
            "google_rating": str(lead.get("google_rating") or ""),
            "review_count": str(lead.get("review_count") or ""),
            "inventory_id": str(lead.get("id", "")),
            "email_subject": lead.get("email_subject", ""),
            "email_body": lead.get("email_body", ""),
        },
    }

    # Add scheduled send time if available
    if lead.get("scheduled_send_at"):
        payload["scheduled_time"] = lead["scheduled_send_at"]

    return payload


def _bulk_upload_to_smartlead(
    campaign_id: str,
    leads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bulk upload leads to a Smartlead campaign. Returns list of successfully uploaded leads."""
    if not SMARTLEAD_API_KEY or not campaign_id:
        return []

    uploaded_leads: list[dict[str, Any]] = []

    for i in range(0, len(leads), SMARTLEAD_BULK_LIMIT):
        batch = leads[i:i + SMARTLEAD_BULK_LIMIT]
        payloads = [_smartlead_lead_payload(lead) for lead in batch]

        try:
            r = httpx.post(
                f"{SMARTLEAD_BASE}/campaigns/{campaign_id}/leads",
                params={"api_key": SMARTLEAD_API_KEY},
                json={"lead_list": payloads},
                timeout=60.0,
            )
            if r.status_code < 300:
                uploaded_leads.extend(batch)
                logger.info("Smartlead bulk upload: %d leads to campaign %s", len(batch), campaign_id)
            else:
                logger.error("Smartlead bulk upload failed (batch %d-%d): %s", i, i + len(batch), r.text[:500])
        except Exception as exc:
            logger.exception("Smartlead bulk upload error (batch %d-%d): %s", i, i + len(batch), exc)

    return uploaded_leads


# ── Add Email Sequences to Campaign ─────────────────────────────────────

def _ensure_campaign_sequence(
    campaign_id: str,
    leads: list[dict[str, Any]],
) -> None:
    """
    Set up the email sequence in the campaign with the generated subject/body.
    Since each lead has its own personalized email, we use Smartlead's
    lead-level email customization via custom fields.
    """
    if not SMARTLEAD_API_KEY or not campaign_id:
        return

    # Check if sequence already exists
    try:
        r = httpx.get(
            f"{SMARTLEAD_BASE}/campaigns/{campaign_id}/sequences",
            params={"api_key": SMARTLEAD_API_KEY},
            timeout=20.0,
        )
        if r.status_code < 300:
            sequences = r.json()
            if sequences:
                return  # Already has sequences
    except Exception:
        pass

    # Create initial sequence step (template — personalization via merge fields)
    try:
        httpx.post(
            f"{SMARTLEAD_BASE}/campaigns/{campaign_id}/sequences",
            params={"api_key": SMARTLEAD_API_KEY},
            json={
                "seq_number": 1,
                "seq_delay_details": {"delay_in_days": 0},
                "subject": "{{email_subject}}",
                "email_body": "{{email_body}}",
                "variant_distribution": [],
            },
            timeout=20.0,
        )
    except Exception as exc:
        logger.warning("Failed to create campaign sequence: %s", exc)


# ── Morning Dispatch Orchestrator ───────────────────────────────────────

def run_morning_dispatch() -> dict[str, Any]:
    """Deprecated — delegates to the mailbox-native rolling dispatcher.

    The old 6:30am Smartlead bulk-upload is gone; instead we simply run one
    rolling-dispatch tick so the day gets started early. Kept under the same
    name so existing scheduler + cron hooks keep working.
    """
    from services.aria_rolling_dispatch import run_rolling_dispatch

    stats = run_rolling_dispatch()
    stats["delegated_from"] = "morning_dispatch"
    _send_dispatch_summary_sms(stats)
    return stats


def _send_dispatch_summary_sms(stats: dict[str, Any]) -> None:
    """Send CEO SMS summary of morning dispatch."""
    try:
        from services.crm_openphone import send_ceo_sms

        total = stats.get("dispatched_total", 0)
        by_vert = stats.get("by_vertical", {})
        parts = [
            f"{v}: {d.get('sent', d.get('dispatched', 0))}"
            for v, d in by_vert.items()
            if isinstance(d, dict)
        ]
        msg = f"ARIA dispatch complete. {total} emails sent.\n" + ", ".join(parts)
        send_ceo_sms(msg)
    except Exception:
        logger.exception("Dispatch summary SMS failed")
