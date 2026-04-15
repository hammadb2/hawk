"""CRM — invite reps (CEO / HoS), resend, deactivate, reassign prospects."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from config import CRM_PUBLIC_BASE_URL, SUPABASE_URL
from routers.crm_auth import require_supabase_uid
from services.crm_portal_stripe import _lookup_user_id_by_email

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
        params={"id": f"eq.{uid}", "select": "id,role,role_type", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _require_privileged(uid: str) -> None:
    """CEO, HoS, or va_manager can invite."""
    p = _profile(uid)
    if not p:
        raise HTTPException(status_code=403, detail="Profile not found")
    role = p.get("role") or ""
    if role in ("ceo", "hos"):
        return
    # va_manager stored in role_type column (role may still be something else)
    if p.get("role_type") == "va_manager":
        return
    raise HTTPException(status_code=403, detail="CEO, HoS, or VA Manager only")


def _is_invite_duplicate_email(resp: httpx.Response) -> bool:
    """Supabase GoTrue rejects invite when auth.users already has this email (portal, tests, etc.)."""
    if resp.status_code not in (400, 409, 422):
        return False
    raw = (resp.text or "").lower()
    try:
        j = resp.json()
    except (json.JSONDecodeError, ValueError):
        return "already" in raw and ("registered" in raw or "exists" in raw)
    if not isinstance(j, dict):
        return False
    code = str(j.get("error_code") or j.get("code") or "").lower()
    msg = str(j.get("msg") or j.get("message") or j.get("error_description") or "").lower()
    if code in ("email_exists", "user_already_exists") or "email_exists" in code or "user_already" in code:
        return True
    if "already" in msg and ("registered" in msg or "exists" in msg or "signed up" in msg):
        return True
    return False


def _get_profile_row(uid: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "id,email,role,status", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _provision_existing_auth_user_as_rep(body: InviteBody) -> dict[str, Any]:
    """
    Email already exists in Supabase Auth — link/update CRM profile and send a magic link so they can sign in.
    """
    email = body.email.lower().strip()
    uid = _lookup_user_id_by_email(email)
    if not uid:
        raise HTTPException(
            status_code=400,
            detail="Invite was rejected for this email, but no existing auth user could be resolved. "
            "Check Supabase Auth users or try a different address.",
        )

    existing = _get_profile_row(uid)
    if existing:
        role = str(existing.get("role") or "").lower()
        if role == "ceo":
            raise HTTPException(status_code=400, detail="This email is already the CEO account.")
        if role == "client":
            raise HTTPException(
                status_code=400,
                detail="This email already has a client portal login. Use a different email for CRM reps.",
            )

    patch: dict[str, Any] = {
        "full_name": body.full_name.strip(),
        "role": body.role,
        "status": "invited",
        "email": email,
    }
    if body.whatsapp_number:
        patch["whatsapp_number"] = body.whatsapp_number.strip()
    # Set role_type for VA roles
    if body.role == "va_manager":
        patch["role_type"] = "va_manager"
    elif body.role == "va":
        patch["role_type"] = "va_outreach"
    if body.team_lead_id:
        patch["team_lead_id"] = body.team_lead_id

    if existing:
        pr = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_sb_headers(),
            params={"id": f"eq.{uid}"},
            json=patch,
            timeout=20.0,
        )
        if pr.status_code >= 400:
            raise HTTPException(status_code=400, detail=pr.text[:500])
    else:
        row = {"id": uid, **patch}
        pr = httpx.post(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_sb_headers(),
            json=row,
            timeout=20.0,
        )
        if pr.status_code >= 400:
            raise HTTPException(status_code=400, detail=pr.text[:500])

    # For VA roles, also create a va_profiles row so RLS user_id linkage works
    if body.role == "va":
        va_row: dict[str, Any] = {
            "user_id": uid,
            "full_name": body.full_name.strip(),
            "email": email,
            "role": "reply_book",
            "status": "active",
        }
        vr = httpx.post(
            f"{SUPABASE_URL}/rest/v1/va_profiles",
            headers={**_sb_headers(), "Prefer": "return=minimal"},
            json=va_row,
            timeout=20.0,
        )
        if vr.status_code >= 400:
            logger.warning("va_profiles upsert for existing user failed: %s %s", vr.status_code, vr.text[:300])

    redir = f"{CRM_PUBLIC_BASE_URL}/crm/onboarding" if CRM_PUBLIC_BASE_URL else None
    recover_json: dict[str, Any] = {"email": email}
    if redir:
        recover_json["options"] = {"email_redirect_to": redir}
    rr = httpx.post(
        f"{SUPABASE_URL}/auth/v1/recover",
        headers=_sb_headers(),
        json=recover_json,
        timeout=30.0,
    )
    if rr.status_code >= 400:
        logger.warning("recover after rep upsert failed: %s %s", rr.status_code, rr.text[:300])

    return {
        "ok": True,
        "existing_user": True,
        "message": "That email already had a login. We set the CRM rep profile and sent a magic link to finish onboarding.",
    }


class InviteBody(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    role: Literal["sales_rep", "team_lead", "va_manager", "va"] = "sales_rep"
    whatsapp_number: str = Field(default="", max_length=40)
    team_lead_id: str | None = None


@router.post("/invite")
def invite_rep(body: InviteBody, uid: str = Depends(require_supabase_uid)):
    _require_privileged(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    meta: dict[str, Any] = {
        "full_name": body.full_name.strip(),
        "crm_role": body.role,
        "crm_initial_status": "invited",
    }
    if body.whatsapp_number:
        meta["whatsapp_number"] = body.whatsapp_number.strip()
    if body.team_lead_id:
        meta["crm_team_lead_id"] = body.team_lead_id
    # Map invite role → profiles.role_type so the auth trigger sets it correctly
    if body.role == "va_manager":
        meta["crm_role_type"] = "va_manager"
    elif body.role == "va":
        meta["crm_role_type"] = "va_outreach"

    # VA roles land on different pages
    if body.role == "va_manager":
        redir = f"{CRM_PUBLIC_BASE_URL}/crm/va/roster" if CRM_PUBLIC_BASE_URL else None
    elif body.role == "va":
        redir = f"{CRM_PUBLIC_BASE_URL}/crm/va/input" if CRM_PUBLIC_BASE_URL else None
    else:
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
        if _is_invite_duplicate_email(r):
            logger.info("invite: email already in Auth, upserting rep profile for %s", body.email)
            return _provision_existing_auth_user_as_rep(body)
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
