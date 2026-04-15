"""CRM — VA Management CRUD router (roster, daily reports, scores, coaching, alerts)."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from routers.crm_auth import require_supabase_uid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/va", tags=["crm-va"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _require_va_privileged(uid: str) -> None:
    """CEO, HoS, or va_manager."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "id,role,role_type", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise HTTPException(status_code=403, detail="Profile not found")
    p = rows[0]
    if p.get("role") in ("ceo", "hos"):
        return
    if p.get("role_type") == "va_manager":
        return
    raise HTTPException(status_code=403, detail="VA manager, CEO, or HoS only")


# ---------------------------------------------------------------------------
# VA Profiles
# ---------------------------------------------------------------------------


class VaProfileBody(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    role: Literal["list_qa", "reply_book"] = "reply_book"
    status: Literal["active", "pip", "inactive"] = "active"


@router.post("/profiles")
def create_va_profile(body: VaProfileBody, uid: str = Depends(require_supabase_uid)):
    _require_va_privileged(uid)
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/va_profiles",
        headers={**_sb_headers(), "Prefer": "return=representation"},
        json={
            "full_name": body.full_name.strip(),
            "email": body.email.lower().strip(),
            "role": body.role,
            "status": body.status,
        },
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])
    return r.json()


class VaStatusBody(BaseModel):
    status: Literal["active", "pip", "inactive"]


@router.patch("/profiles/{va_id}/status")
def update_va_status(va_id: str, body: VaStatusBody, uid: str = Depends(require_supabase_uid)):
    _require_va_privileged(uid)
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/va_profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{va_id}"},
        json={"status": body.status},
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Deactivate VA — sets inactive + revokes Supabase auth
# ---------------------------------------------------------------------------


def _get_caller_profile(uid: str) -> dict[str, Any]:
    """Return caller's profile row."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "id,role,role_type", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise HTTPException(status_code=403, detail="Profile not found")
    return rows[0]


def _get_va_profile(va_id: str) -> dict[str, Any]:
    """Return va_profiles row by id."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/va_profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{va_id}", "select": "id,user_id,full_name,email,role,status", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise HTTPException(status_code=404, detail="VA not found")
    return rows[0]


def _ban_auth_user(user_id: str) -> None:
    """Ban a Supabase auth user (effectively disables login permanently)."""
    r = httpx.put(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers=_sb_headers(),
        json={"ban_duration": "876600h"},  # ~100 years
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.warning("ban auth user %s failed: %s %s", user_id, r.status_code, r.text[:300])


class DeactivateVaBody(BaseModel):
    va_id: str


@router.post("/deactivate")
def deactivate_va(body: DeactivateVaBody, uid: str = Depends(require_supabase_uid)):
    """Deactivate a VA — set inactive + revoke auth. VA managers can only deactivate VAs, not other managers."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    caller = _get_caller_profile(uid)
    caller_role = caller.get("role") or ""
    is_ceo_or_hos = caller_role in ("ceo", "hos")
    is_va_manager = caller.get("role_type") == "va_manager"

    if not is_ceo_or_hos and not is_va_manager:
        raise HTTPException(status_code=403, detail="VA manager, CEO, or HoS only")

    va = _get_va_profile(body.va_id)

    # va_manager can only deactivate VAs — not other va_managers or higher
    if is_va_manager and not is_ceo_or_hos:
        va_user_id = va.get("user_id")
        if va_user_id:
            # Check the profiles row to ensure target is a plain VA
            pr = httpx.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=_sb_headers(),
                params={"id": f"eq.{va_user_id}", "select": "id,role,role_type", "limit": "1"},
                timeout=20.0,
            )
            pr.raise_for_status()
            target_profiles = pr.json()
            if target_profiles:
                tp = target_profiles[0]
                if tp.get("role") in ("ceo", "hos", "team_lead") or tp.get("role_type") == "va_manager":
                    raise HTTPException(status_code=403, detail="VA managers cannot deactivate non-VA users")

    # 1. Set va_profiles.status = inactive
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/va_profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{body.va_id}"},
        json={"status": "inactive"},
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])

    # 2. Also set profiles.status = inactive and ban auth user
    va_user_id = va.get("user_id")
    if va_user_id:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_sb_headers(),
            params={"id": f"eq.{va_user_id}"},
            json={"status": "inactive"},
            timeout=20.0,
        )
        _ban_auth_user(va_user_id)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Coaching notes
# ---------------------------------------------------------------------------


class CoachingNoteBody(BaseModel):
    va_id: str
    note: str = Field(..., min_length=1)
    type: Literal["coaching", "pip", "commendation"] = "coaching"


@router.post("/coaching-notes")
def add_coaching_note(body: CoachingNoteBody, uid: str = Depends(require_supabase_uid)):
    _require_va_privileged(uid)
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/va_coaching_notes",
        headers={**_sb_headers(), "Prefer": "return=representation"},
        json={
            "va_id": body.va_id,
            "manager_id": uid,
            "note": body.note.strip(),
            "type": body.type,
        },
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])
    return r.json()


# ---------------------------------------------------------------------------
# Alerts — acknowledge
# ---------------------------------------------------------------------------


class AckAlertBody(BaseModel):
    alert_id: str


@router.post("/alerts/acknowledge")
def acknowledge_alert(body: AckAlertBody, uid: str = Depends(require_supabase_uid)):
    _require_va_privileged(uid)
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/va_alerts",
        headers=_sb_headers(),
        params={"id": f"eq.{body.alert_id}"},
        json={"acknowledged": True},
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Bonus tracker — monthly call averages + bonus tiers
# ---------------------------------------------------------------------------

BONUS_TIERS = [
    (30, 2000),   # 30+ avg calls/day → $2,000
    (25, 1500),   # 25-29 → $1,500
    (20, 1000),   # 20-24 → $1,000
    (15, 500),    # 15-19 → $500
]


@router.get("/bonus/{va_id}")
def get_va_bonus(va_id: str, uid: str = Depends(require_supabase_uid)):
    _require_va_privileged(uid)
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/va_daily_reports",
        headers=_sb_headers(),
        params={
            "va_id": f"eq.{va_id}",
            "select": "report_date,calls_booked",
            "order": "report_date.desc",
            "limit": "90",
        },
        timeout=30.0,
    )
    r.raise_for_status()
    rows = r.json() or []
    if not rows:
        return {"months": [], "current_projection": None}

    # group by month
    from collections import defaultdict
    by_month: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        month = str(row.get("report_date", ""))[:7]
        by_month[month].append(row.get("calls_booked", 0))

    months = []
    for month, calls in sorted(by_month.items(), reverse=True):
        avg = sum(calls) / len(calls) if calls else 0
        bonus = 0
        for threshold, amount in BONUS_TIERS:
            if avg >= threshold:
                bonus = amount
                break
        months.append({
            "month": month,
            "avg_calls_per_day": round(avg, 1),
            "days_reported": len(calls),
            "bonus_amount": bonus,
        })

    return {"months": months, "current_projection": months[0] if months else None}
