"""CRM — Team documents, personal details, bank details + signed URL generation."""

from __future__ import annotations

import logging
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.crm_auth import require_supabase_uid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/team", tags=["crm-team-docs"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _get_caller_profile(uid: str) -> dict:
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


def _can_access_profile(caller: dict, target_profile_id: str) -> bool:
    """Check if caller can access target profile's documents/details."""
    caller_id = caller.get("id", "")
    caller_role = caller.get("role", "")
    caller_role_type = caller.get("role_type", "")

    # Own profile
    if caller_id == target_profile_id:
        return True

    # CEO or HoS — full access
    if caller_role in ("ceo", "hos"):
        return True

    # VA manager — can access VA profiles only
    if caller_role_type == "va_manager":
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_sb_headers(),
            params={"id": f"eq.{target_profile_id}", "select": "id,role_type", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows and rows[0].get("role_type") in ("va_outreach",):
            return True

    return False


def _require_access(uid: str, target_profile_id: str) -> dict:
    """Raise 403 if caller cannot access target profile."""
    caller = _get_caller_profile(uid)
    if not _can_access_profile(caller, target_profile_id):
        raise HTTPException(status_code=403, detail="You do not have access to this profile")
    return caller


# ---------------------------------------------------------------------------
# Signed URL generation for team-documents bucket
# ---------------------------------------------------------------------------


class SignedUrlRequest(BaseModel):
    file_path: str


@router.post("/documents/signed-url")
def create_signed_url(body: SignedUrlRequest, uid: str = Depends(require_supabase_uid)):
    """Generate a signed URL for a file in the team-documents bucket. Expires in 60 minutes."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Extract profile_id from file path (format: {profile_id}/filename)
    parts = body.file_path.split("/", 1)
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid file path")

    target_profile_id = parts[0]
    _require_access(uid, target_profile_id)

    # Create signed URL via Supabase Storage API
    r = httpx.post(
        f"{SUPABASE_URL}/storage/v1/object/sign/team-documents/{body.file_path}",
        headers=_sb_headers(),
        json={"expiresIn": 3600},  # 60 minutes
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Failed to create signed URL: {r.text[:300]}")

    data = r.json()
    signed_url = data.get("signedURL", "")
    if signed_url and not signed_url.startswith("http"):
        signed_url = f"{SUPABASE_URL}/storage/v1{signed_url}"

    return {"signed_url": signed_url}


# ---------------------------------------------------------------------------
# Document delete (CEO only via API for extra safety)
# ---------------------------------------------------------------------------


class DeleteDocRequest(BaseModel):
    document_id: str
    file_path: str


@router.post("/documents/delete")
def delete_document(body: DeleteDocRequest, uid: str = Depends(require_supabase_uid)):
    """Delete a document record and its storage file. CEO/HoS only."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    caller = _get_caller_profile(uid)
    if caller.get("role") not in ("ceo", "hos"):
        raise HTTPException(status_code=403, detail="Only CEO/HoS can delete documents")

    # Delete from storage
    r = httpx.delete(
        f"{SUPABASE_URL}/storage/v1/object/team-documents/{body.file_path}",
        headers=_sb_headers(),
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.warning("Storage delete failed: %s %s", r.status_code, r.text[:300])

    # Delete from team_documents table
    r2 = httpx.delete(
        f"{SUPABASE_URL}/rest/v1/team_documents",
        headers=_sb_headers(),
        params={"id": f"eq.{body.document_id}"},
        timeout=20.0,
    )
    if r2.status_code >= 400:
        raise HTTPException(status_code=400, detail=r2.text[:300])

    return {"ok": True}


# ---------------------------------------------------------------------------
# Bank details visibility check
# ---------------------------------------------------------------------------


@router.get("/bank-details-access/{profile_id}")
def check_bank_details_access(profile_id: str, uid: str = Depends(require_supabase_uid)):
    """Check if the caller can see bank details for a given profile."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    caller = _get_caller_profile(uid)
    can_access = _can_access_profile(caller, profile_id)
    return {"can_access": can_access}
