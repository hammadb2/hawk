"""CRM — invite reps (CEO), resend, deactivate, reassign prospects."""

from __future__ import annotations

import logging
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from config import CRM_PUBLIC_BASE_URL, SUPABASE_URL
from routers.crm_auth import require_supabase_uid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm", tags=["crm-invite"])

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _profile(uid: str) -> dict | None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "id,role", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _require_privileged(uid: str) -> None:
    p = _profile(uid)
    if not p or p.get("role") not in ("ceo", "hos"):
        raise HTTPException(status_code=403, detail="CEO or HoS only")


class InviteBody(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    role: Literal["sales_rep", "team_lead"] = "sales_rep"
    whatsapp_number: str = Field(..., min_length=5, max_length=40)
    team_lead_id: str | None = None


@router.post("/invite")
def invite_rep(body: InviteBody, uid: str = Depends(require_supabase_uid)):
    _require_privileged(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    meta = {
        "full_name": body.full_name.strip(),
        "crm_role": body.role,
        "crm_initial_status": "invited",
        "whatsapp_number": body.whatsapp_number.strip(),
    }
    if body.team_lead_id:
        meta["crm_team_lead_id"] = body.team_lead_id

    redir = f"{CRM_PUBLIC_BASE_URL}/crm/onboarding" if CRM_PUBLIC_BASE_URL else None
    payload: dict = {"email": body.email.lower().strip(), "data": meta}
    if redir:
        payload["options"] = {"email_redirect_to": redir}

    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/invite",
        headers=_sb_headers(),
        json=payload,
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("invite failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=400, detail=r.text[:500])
    return {"ok": True, "message": "Invite sent"}


class ResendBody(BaseModel):
    email: EmailStr


@router.post("/invite/resend")
def resend_invite(body: ResendBody, uid: str = Depends(require_supabase_uid)):
    _require_privileged(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Magic link for existing users (re-invite flow)
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/recover",
        headers=_sb_headers(),
        json={"email": body.email.lower().strip()},
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("resend recover failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=400, detail=r.text[:500])
    return {"ok": True, "message": "Recovery email sent"}


class DeactivateBody(BaseModel):
    profile_id: str


@router.post("/rep/deactivate")
def deactivate_rep(body: DeactivateBody, uid: str = Depends(require_supabase_uid)):
    _require_privileged(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{body.profile_id}"},
        json={"status": "inactive"},
        timeout=20.0,
    )
    r.raise_for_status()
    return {"ok": True}


class ReassignBody(BaseModel):
    from_rep_id: str
    to_rep_id: str


@router.post("/rep/reassign-prospects")
def reassign_prospects(body: ReassignBody, uid: str = Depends(require_supabase_uid)):
    _require_privileged(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={"assigned_rep_id": f"eq.{body.from_rep_id}"},
        json={"assigned_rep_id": body.to_rep_id},
        timeout=60.0,
    )
    r.raise_for_status()
    return {"ok": True}
