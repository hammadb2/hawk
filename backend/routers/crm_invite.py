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
        "whatsapp_number": body.whatsapp_number.strip(),
        "status": "invited",
        "email": email,
        "onboarding_status": "not_started",
    }
    if body.team_lead_id:
        patch["team_lead_id"] = body.team_lead_id
    if body.role_type:
        patch["role_type"] = body.role_type

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

    redir = f"{CRM_PUBLIC_BASE_URL}/onboarding" if CRM_PUBLIC_BASE_URL else None
    recover_json: dict[str, Any] = {"email": email}

    # Create onboarding session with agreed_terms for existing user
    if body.agreed_terms and SUPABASE_URL and SERVICE_KEY:
        _create_onboarding_session(uid, body.agreed_terms, _sb_headers())
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


def _create_onboarding_session(profile_id: str, agreed_terms: dict[str, Any], headers: dict[str, str]) -> None:
    """Create an onboarding session with agreed_terms for a newly invited user."""
    try:
        payload = {
            "profile_id": profile_id,
            "status": "not_started",
            "current_step": 0,
            "agreed_terms": agreed_terms,
        }
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
            headers={**headers, "Prefer": "return=representation"},
            json=payload,
            timeout=20.0,
        )
    except Exception as exc:
        logger.warning("Failed to create onboarding session: %s", exc)


class InviteBody(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    role: Literal["sales_rep", "team_lead", "closer", "client"] = "sales_rep"
    role_type: Literal["ceo", "closer", "va_outreach", "va_manager", "csm", "client", "sales_rep", "team_lead"] | None = None
    whatsapp_number: str = Field(..., min_length=5, max_length=40)
    team_lead_id: str | None = None
    agreed_terms: dict[str, Any] | None = None


@router.post("/invite")
def invite_rep(body: InviteBody, uid: str = Depends(require_supabase_uid)):
    _require_privileged(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    meta: dict[str, Any] = {
        "full_name": body.full_name.strip(),
        "crm_role": body.role,
        "crm_initial_status": "invited",
        "whatsapp_number": body.whatsapp_number.strip(),
    }
    if body.team_lead_id:
        meta["crm_team_lead_id"] = body.team_lead_id
    if body.role_type:
        meta["crm_role_type"] = body.role_type

    # Create onboarding session with agreed_terms if provided
    redir = f"{CRM_PUBLIC_BASE_URL}/onboarding" if CRM_PUBLIC_BASE_URL else None
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

    # Create onboarding session with agreed_terms for newly invited user
    if body.agreed_terms:
        # The auth user was just created — look up the new user ID
        try:
            new_uid = _lookup_user_id_by_email(body.email.lower().strip())
            if new_uid and SUPABASE_URL and SERVICE_KEY:
                # Set role_type on profile if provided
                prof_patch: dict[str, Any] = {"onboarding_status": "not_started"}
                if body.role_type:
                    prof_patch["role_type"] = body.role_type
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/profiles",
                    headers=_sb_headers(),
                    params={"id": f"eq.{new_uid}"},
                    json=prof_patch,
                    timeout=20.0,
                )
                _create_onboarding_session(new_uid, body.agreed_terms, _sb_headers())
        except Exception as exc:
            logger.warning("Failed to create onboarding session for new invite: %s", exc)

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
