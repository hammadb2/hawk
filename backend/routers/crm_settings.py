"""CRM settings — consolidated key/value config for the whole app.

All settings (pipeline caps, feature flags, campaign IDs, cron toggles, etc.)
live in the existing `public.crm_settings` key/value table so every value is
hot-reloadable without a deploy. This router is the single authenticated
read/write surface for the /crm/settings UI and anywhere else the frontend
needs structured access.

Auth: CEO-only. Verifies the caller's Supabase JWT, looks up their profile,
and rejects anything non-CEO with 403.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from routers.crm_auth import require_supabase_uid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/settings", tags=["crm-settings"])


def _service_headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def require_ceo(uid: str = Depends(require_supabase_uid)) -> str:
    """Verifies the authenticated user has role=ceo. Returns their uid."""
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_service_headers(),
            params={"id": f"eq.{uid}", "select": "role", "limit": "1"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json() or []
    except Exception as exc:
        logger.warning("profile lookup failed for uid=%s: %s", uid, exc)
        raise HTTPException(status_code=503, detail="Profile lookup failed")
    if not rows or rows[0].get("role") != "ceo":
        raise HTTPException(status_code=403, detail="CEO role required")
    return uid


# Known keys + safe default values. Anything not in this list is still readable
# if present but new defaults won't be inserted unless the migration runs.
# Keep in sync with supabase/migrations/*_crm_settings_defaults.sql.
DEFAULT_KEYS: dict[str, str] = {
    # Pipeline — dispatch
    "pipeline_dispatch_enabled": "true",
    "pipeline_nightly_enabled": "true",
    "daily_cap_dental": "200",
    "daily_cap_legal": "200",
    "daily_cap_accounting": "200",
    "daily_send_limit": "600",
    "per_inbox_daily_cap": "50",
    "dispatch_window_start_hour": "9",
    "dispatch_window_end_hour": "16",
    # Pipeline — scanner
    "score_soft_drop_threshold": "85",
    "sla_new_stage_minutes": "10",
    "sla_scan_concurrency": "3",
    # Pipeline — discovery
    "google_places_cities": (
        '["Toronto","Vancouver","Calgary","Edmonton","Ottawa","Montreal",'
        '"Winnipeg","Halifax","Quebec City","Saskatoon","Regina","Victoria",'
        '"Kelowna","London","Hamilton","Waterloo","Mississauga","Brampton"]'
    ),
    "google_places_max_per_search": "10",
    "discovery_verticals_enabled": '["dental","legal","accounting"]',
    "apify_enable_leadsfinder": "true",
    "apify_enable_linkedin": "true",
    "apify_enable_website_crawler": "false",
    # Smartlead campaigns
    "smartlead_campaign_id_dental": "",
    "smartlead_campaign_id_legal": "",
    "smartlead_campaign_id_accounting": "",
    # Team & commissions
    "commission_rate": "0.3",
    "monthly_close_target": "10",
    "aging_days_warning": "3",
    "aging_days_critical": "7",
    "guarantee_days": "90",
    "auto_assign_enabled": "true",
    # Notifications
    "ceo_phone": "",
    "slack_webhook_url": "",
    "notify_on_scan_fail": "true",
    "notify_on_dispatch_fail": "true",
    "notify_on_pipeline_fail": "true",
    # Branding / general
    "company_name": "HAWK Security",
    "support_email": "support@securedbyhawk.com",
    "timezone": "America/Edmonton",
}


class Setting(BaseModel):
    key: str
    value: str


class SettingsResponse(BaseModel):
    settings: dict[str, str]
    defaults: dict[str, str]


class BulkUpdatePayload(BaseModel):
    updates: dict[str, str]


@router.get("", response_model=SettingsResponse)
def get_all_settings(_: str = Depends(require_ceo)) -> dict[str, Any]:
    """Return every crm_settings row as a flat dict plus the known defaults."""
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_service_headers(),
            params={"select": "key,value", "limit": "1000"},
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json() or []
    except Exception as exc:
        logger.exception("settings fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail="Failed to read settings")

    settings = {str(row["key"]): str(row.get("value") or "") for row in rows if row.get("key")}
    # Surface every known key so the UI can render unset fields with their default.
    for k, v in DEFAULT_KEYS.items():
        settings.setdefault(k, v)
    return {"settings": settings, "defaults": DEFAULT_KEYS}


@router.patch("")
def update_settings(
    payload: BulkUpdatePayload,
    _: str = Depends(require_ceo),
) -> dict[str, Any]:
    """Bulk upsert — one row per key. Rows are coerced to strings."""
    if not payload.updates:
        return {"ok": True, "updated": 0}

    rows = [{"key": k, "value": "" if v is None else str(v)} for k, v in payload.updates.items() if k]
    if not rows:
        return {"ok": True, "updated": 0}

    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers={**_service_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            params={"on_conflict": "key"},
            json=rows,
            timeout=20.0,
        )
        r.raise_for_status()
    except Exception as exc:
        logger.exception("settings upsert failed: %s", exc)
        raise HTTPException(status_code=503, detail="Failed to save settings")

    return {"ok": True, "updated": len(rows)}


@router.post("/reset")
def reset_to_defaults(_: str = Depends(require_ceo)) -> dict[str, Any]:
    """Danger-zone: overwrite every known key with its default value.

    Unknown keys (ones not in DEFAULT_KEYS) are left untouched so we don't
    wipe third-party keys written by future migrations.
    """
    rows = [{"key": k, "value": v} for k, v in DEFAULT_KEYS.items()]
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers={**_service_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            params={"on_conflict": "key"},
            json=rows,
            timeout=20.0,
        )
        r.raise_for_status()
    except Exception as exc:
        logger.exception("settings reset failed: %s", exc)
        raise HTTPException(status_code=503, detail="Failed to reset settings")
    return {"ok": True, "reset_keys": len(rows)}
