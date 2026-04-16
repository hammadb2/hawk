"""CRM — AI Onboarding Portal API endpoints."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from config import SUPABASE_URL, OPENAI_API_KEY, OPENAI_MODEL
from routers.crm_auth import require_supabase_uid
from services.crm_portal_email import send_resend, _wrap, _esc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/onboarding", tags=["crm-onboarding"])

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _get_profile(uid: str) -> dict[str, Any] | None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _require_ceo_or_va_manager(uid: str) -> dict[str, Any]:
    """Returns the profile if user is CEO or VA manager."""
    prof = _get_profile(uid)
    if not prof:
        raise HTTPException(status_code=403, detail="Profile not found")
    role = prof.get("role", "")
    role_type = prof.get("role_type", "")
    if role != "ceo" and role_type != "va_manager":
        raise HTTPException(status_code=403, detail="CEO or VA Manager only")
    return prof


# ── Session management ────────────────────────────────────────────────────

@router.get("/session")
def get_or_create_session(uid: str = Depends(require_supabase_uid)):
    """Get or create onboarding session for the current user."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()

    # Check existing session
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"profile_id": f"eq.{uid}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if rows:
        return rows[0]

    # Create new session
    prof = _get_profile(uid)
    agreed_terms = {}
    if prof:
        # Check if agreed_terms were set during invite
        r2 = httpx.get(
            f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
            headers=headers,
            params={"profile_id": f"eq.{uid}", "select": "agreed_terms", "limit": "1"},
            timeout=20.0,
        )
        if r2.status_code == 200 and r2.json():
            agreed_terms = r2.json()[0].get("agreed_terms", {})

    payload = {
        "profile_id": uid,
        "status": "in_progress",
        "current_step": 1,
        "agreed_terms": agreed_terms,
    }
    r3 = httpx.post(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers={**headers, "Prefer": "return=representation"},
        json=payload,
        timeout=20.0,
    )
    if r3.status_code >= 400:
        # Might be a race condition — try to fetch again
        r4 = httpx.get(
            f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
            headers=headers,
            params={"profile_id": f"eq.{uid}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r4.raise_for_status()
        rows2 = r4.json()
        if rows2:
            return rows2[0]
        raise HTTPException(status_code=400, detail=r3.text[:500])

    # Update profile onboarding_status
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"id": f"eq.{uid}"},
        json={"onboarding_status": "in_progress", "status": "onboarding"},
        timeout=20.0,
    )

    created = r3.json()
    return created[0] if isinstance(created, list) else created


class UpdateStepBody(BaseModel):
    current_step: int


@router.patch("/session/step")
def update_session_step(body: UpdateStepBody, uid: str = Depends(require_supabase_uid)):
    """Update the current step of the onboarding session."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"profile_id": f"eq.{uid}"},
        json={"current_step": body.current_step},
        timeout=20.0,
    )
    r.raise_for_status()
    return {"ok": True}


# ── Personal details ──────────────────────────────────────────────────────

class PersonalDetailsBody(BaseModel):
    phone: str | None = None
    whatsapp: str | None = None
    address: str | None = None
    country: str | None = None
    date_of_birth: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


@router.post("/personal-details")
def save_personal_details(body: PersonalDetailsBody, uid: str = Depends(require_supabase_uid)):
    """Save personal details during onboarding step 2."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()
    payload: dict[str, Any] = {
        "profile_id": uid,
        "phone": body.phone,
        "whatsapp": body.whatsapp,
        "address": body.address,
        "country": body.country,
        "emergency_contact_name": body.emergency_contact_name,
        "emergency_contact_phone": body.emergency_contact_phone,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.date_of_birth:
        payload["date_of_birth"] = body.date_of_birth

    # Upsert
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/team_personal_details",
        headers={**headers, "Prefer": "return=representation,resolution=merge-duplicates"},
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])

    # Update submission flag
    _ensure_submission(uid, headers, personal_details_submitted=True)

    return {"ok": True}


# ── Bank details ──────────────────────────────────────────────────────────

class BankDetailsBody(BaseModel):
    full_name: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    routing_or_swift: str | None = None
    payment_method: str | None = None
    notes: str | None = None


@router.post("/bank-details")
def save_bank_details(body: BankDetailsBody, uid: str = Depends(require_supabase_uid)):
    """Save bank details during onboarding step 4."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()
    payload: dict[str, Any] = {
        "profile_id": uid,
        "full_name": body.full_name,
        "bank_name": body.bank_name,
        "account_number": body.account_number,
        "routing_or_swift": body.routing_or_swift,
        "payment_method": body.payment_method,
        "notes": body.notes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/team_bank_details",
        headers={**headers, "Prefer": "return=representation,resolution=merge-duplicates"},
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])

    _ensure_submission(uid, headers, bank_details_submitted=True)

    return {"ok": True}


def _ensure_submission(
    uid: str,
    headers: dict[str, str],
    personal_details_submitted: bool | None = None,
    bank_details_submitted: bool | None = None,
    government_id_url: str | None = None,
) -> None:
    """Ensure an onboarding_submissions row exists and update flags."""
    # Get session ID
    sr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"profile_id": f"eq.{uid}", "select": "id", "limit": "1"},
        timeout=20.0,
    )
    sr.raise_for_status()
    sessions = sr.json()
    if not sessions:
        return
    session_id = sessions[0]["id"]

    patch: dict[str, Any] = {"session_id": session_id}
    if personal_details_submitted is not None:
        patch["personal_details_submitted"] = personal_details_submitted
    if bank_details_submitted is not None:
        patch["bank_details_submitted"] = bank_details_submitted
    if government_id_url is not None:
        patch["government_id_url"] = government_id_url

    httpx.post(
        f"{SUPABASE_URL}/rest/v1/onboarding_submissions",
        headers={**headers, "Prefer": "return=representation,resolution=merge-duplicates"},
        json=patch,
        timeout=20.0,
    )


# ── Government ID upload ──────────────────────────────────────────────────

@router.post("/upload-gov-id")
async def upload_government_id(
    request: Request,
    file: UploadFile = File(...),
    uid: str = Depends(require_supabase_uid),
):
    """Upload government-issued ID during onboarding step 3."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "pdf"):
        raise HTTPException(status_code=400, detail="Only JPG, PNG, or PDF accepted")

    content_type = file.content_type or f"image/{ext}"
    if ext == "pdf":
        content_type = "application/pdf"

    path = f"{uid}/gov-id.{ext}"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/onboarding-documents/{path}"

    r = httpx.put(
        upload_url,
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": content_type,
            "x-upsert": "true",
        },
        content=content,
        timeout=60.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Upload failed: {r.text[:300]}")

    file_url = f"{SUPABASE_URL}/storage/v1/object/onboarding-documents/{path}"

    headers_sb = _sb_headers()
    _ensure_submission(uid, headers_sb, government_id_url=file_url)

    return {"ok": True, "file_url": file_url}


# ── Document signing ──────────────────────────────────────────────────────

class SignDocumentBody(BaseModel):
    document_type: Literal["contract", "nda", "acceptable_use"]
    signature_data: str  # base64 drawn signature
    ip_address: str | None = None


@router.post("/sign-document")
def sign_document(body: SignDocumentBody, request: Request, uid: str = Depends(require_supabase_uid)):
    """Record e-signature for a document during onboarding step 5."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()

    # Get session
    sr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"profile_id": f"eq.{uid}", "select": "id", "limit": "1"},
        timeout=20.0,
    )
    sr.raise_for_status()
    sessions = sr.json()
    if not sessions:
        raise HTTPException(status_code=400, detail="No onboarding session found")
    session_id = sessions[0]["id"]

    ip = body.ip_address or request.client.host if request.client else "unknown"

    payload = {
        "session_id": session_id,
        "document_type": body.document_type,
        "signature_data": body.signature_data,
        "ip_address": ip,
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/onboarding_documents",
        headers={**headers, "Prefer": "return=representation"},
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])

    return {"ok": True}


# ── Quiz results ──────────────────────────────────────────────────────────

class QuizResultBody(BaseModel):
    module: str
    score: int
    passed: bool


@router.post("/quiz-result")
def save_quiz_result(body: QuizResultBody, uid: str = Depends(require_supabase_uid)):
    """Save a quiz result during onboarding step 6."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()

    sr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"profile_id": f"eq.{uid}", "select": "id", "limit": "1"},
        timeout=20.0,
    )
    sr.raise_for_status()
    sessions = sr.json()
    if not sessions:
        raise HTTPException(status_code=400, detail="No onboarding session found")
    session_id = sessions[0]["id"]

    payload = {
        "session_id": session_id,
        "module": body.module,
        "score": body.score,
        "passed": body.passed,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/onboarding_quiz_results",
        headers={**headers, "Prefer": "return=representation"},
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])

    return {"ok": True}


# ── Submit for review ─────────────────────────────────────────────────────

@router.post("/submit")
def submit_for_review(uid: str = Depends(require_supabase_uid)):
    """Submit onboarding for review — sets status to pending_review."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()
    now = datetime.now(timezone.utc).isoformat()

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"profile_id": f"eq.{uid}"},
        json={"status": "pending_review", "completed_at": now},
        timeout=20.0,
    )
    r.raise_for_status()

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"id": f"eq.{uid}"},
        json={"onboarding_status": "pending_review"},
        timeout=20.0,
    )

    # Send notification email to approver
    _notify_approver(uid, headers)

    return {"ok": True}


def _notify_approver(hire_uid: str, headers: dict[str, str]) -> None:
    """Send email to the appropriate approver."""
    try:
        prof = _get_profile(hire_uid)
        if not prof:
            return

        role_type = prof.get("role_type", "closer")
        hire_name = prof.get("full_name") or prof.get("email") or "New hire"

        # VA roles → va_manager approves; all others → CEO approves
        if role_type in ("va_outreach",):
            # Find VA manager(s)
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=headers,
                params={
                    "role_type": "eq.va_manager",
                    "status": "eq.active",
                    "select": "email",
                    "limit": "10",
                },
                timeout=20.0,
            )
            r.raise_for_status()
            approvers = [row["email"] for row in r.json() if row.get("email")]
        else:
            # CEO approves
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=headers,
                params={
                    "role": "eq.ceo",
                    "select": "email",
                    "limit": "1",
                },
                timeout=20.0,
            )
            r.raise_for_status()
            approvers = [row["email"] for row in r.json() if row.get("email")]

        from config import CRM_PUBLIC_BASE_URL
        review_url = f"{CRM_PUBLIC_BASE_URL}/crm/onboarding/review"

        for email in approvers:
            inner = f"""
              <tr>
                <td style="padding:40px 48px 32px;">
                  <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
                    Onboarding Submission
                  </p>
                  <p style="margin:0 0 24px;font-size:15px;color:#9090A8;line-height:1.6;">
                    <strong style="color:#00C48C;">{_esc(hire_name)}</strong> has completed their
                    onboarding and is waiting for your review.
                  </p>
                  <table cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td align="center">
                        <a href="{_esc(review_url)}"
                           style="display:inline-block;background:#00C48C;color:#ffffff;
                                  font-size:15px;font-weight:700;text-decoration:none;
                                  padding:16px 48px;border-radius:8px;letter-spacing:0.3px;">
                          Review Submission
                        </a>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
"""
            send_resend(
                to_email=email,
                subject=f"Onboarding review needed: {hire_name}",
                html=_wrap(inner),
                tags=[{"name": "category", "value": "onboarding_review"}],
            )
    except Exception as exc:
        logger.exception("Failed to notify approver: %s", exc)


# ── Approval / rejection (CEO or VA manager) ─────────────────────────────

class ReviewBody(BaseModel):
    session_id: str
    action: Literal["approve", "reject"]
    reason: str | None = None


@router.post("/review")
def review_submission(body: ReviewBody, uid: str = Depends(require_supabase_uid)):
    """Approve or reject an onboarding submission."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    reviewer = _require_ceo_or_va_manager(uid)
    headers = _sb_headers()
    now = datetime.now(timezone.utc).isoformat()

    # Get the session to check role access
    sr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"id": f"eq.{body.session_id}", "select": "id,profile_id,status", "limit": "1"},
        timeout=20.0,
    )
    sr.raise_for_status()
    sessions = sr.json()
    if not sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[0]

    if session["status"] != "pending_review":
        raise HTTPException(status_code=400, detail="Session is not pending review")

    # VA manager can only approve VA roles
    hire_profile = _get_profile(session["profile_id"])
    if not hire_profile:
        raise HTTPException(status_code=404, detail="Hire profile not found")

    if reviewer.get("role") != "ceo" and reviewer.get("role_type") == "va_manager":
        if hire_profile.get("role_type") not in ("va_outreach", "va_manager"):
            raise HTTPException(status_code=403, detail="VA Manager can only review VA onboarding")

    if body.action == "approve":
        patch = {
            "status": "approved",
            "approved_by": uid,
            "approved_at": now,
        }
        profile_patch = {
            "onboarding_status": "approved",
            "status": "active",
        }
    else:
        patch = {
            "status": "rejected",
            "rejected_reason": body.reason or "No reason provided",
        }
        profile_patch = {
            "onboarding_status": "rejected",
        }

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"id": f"eq.{body.session_id}"},
        json=patch,
        timeout=20.0,
    ).raise_for_status()

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"id": f"eq.{session['profile_id']}"},
        json=profile_patch,
        timeout=20.0,
    ).raise_for_status()

    # Notify the hire
    if body.action == "reject" and hire_profile.get("email"):
        _send_rejection_email(hire_profile["email"], hire_profile.get("full_name", ""), body.reason or "")

    return {"ok": True, "action": body.action}


def _send_rejection_email(to_email: str, name: str, reason: str) -> None:
    try:
        inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
                Onboarding Update
              </p>
              <p style="margin:0 0 24px;font-size:15px;color:#9090A8;line-height:1.6;">
                Hi {_esc(name)}, your onboarding submission needs revision.
              </p>
              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:24px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #FF4444;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#FF4444;">
                      Reason
                    </p>
                    <p style="margin:0;font-size:13px;color:#ffffff;line-height:1.5;">
                      {_esc(reason)}
                    </p>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 24px;font-size:15px;color:#9090A8;line-height:1.6;">
                Please log in to your onboarding portal to address the feedback and resubmit.
              </p>
            </td>
          </tr>
"""
        send_resend(
            to_email=to_email,
            subject="Action required: onboarding revision needed",
            html=_wrap(inner),
            tags=[{"name": "category", "value": "onboarding_rejection"}],
        )
    except Exception as exc:
        logger.exception("Failed to send rejection email: %s", exc)


# ── Review queue listing ──────────────────────────────────────────────────

@router.get("/review/list")
def list_review_queue(
    status: str | None = None,
    uid: str = Depends(require_supabase_uid),
):
    """List onboarding sessions for the review queue."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    reviewer = _require_ceo_or_va_manager(uid)
    headers = _sb_headers()

    params: dict[str, str] = {
        "select": "id,profile_id,status,agreed_terms,current_step,completed_at,approved_by,approved_at,rejected_reason,created_at",
        "order": "created_at.desc",
        "limit": "100",
    }
    if status:
        params["status"] = f"eq.{status}"

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params=params,
        timeout=30.0,
    )
    r.raise_for_status()
    sessions = r.json()

    # Enrich with profile info
    profile_ids = list({s["profile_id"] for s in sessions})
    profiles_map: dict[str, dict] = {}
    if profile_ids:
        for pid in profile_ids:
            pr = httpx.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers=headers,
                params={"id": f"eq.{pid}", "select": "id,full_name,email,role,role_type", "limit": "1"},
                timeout=20.0,
            )
            if pr.status_code == 200 and pr.json():
                profiles_map[pid] = pr.json()[0]

    # VA manager can only see VA sessions
    result = []
    for s in sessions:
        prof_info = profiles_map.get(s["profile_id"], {})
        if reviewer.get("role") != "ceo" and reviewer.get("role_type") == "va_manager":
            if prof_info.get("role_type") not in ("va_outreach", "va_manager"):
                continue
        result.append({**s, "profile": prof_info})

    return result


@router.get("/review/{session_id}")
def get_review_detail(session_id: str, uid: str = Depends(require_supabase_uid)):
    """Get full detail for a single onboarding submission."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    _require_ceo_or_va_manager(uid)
    headers = _sb_headers()

    # Session
    sr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"id": f"eq.{session_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    sr.raise_for_status()
    sessions = sr.json()
    if not sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[0]
    profile_id = session["profile_id"]

    # Profile
    prof = _get_profile(profile_id) or {}

    # Personal details
    pd_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/team_personal_details",
        headers=headers,
        params={"profile_id": f"eq.{profile_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    personal = pd_r.json()[0] if pd_r.status_code == 200 and pd_r.json() else None

    # Bank details
    bd_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/team_bank_details",
        headers=headers,
        params={"profile_id": f"eq.{profile_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    bank = bd_r.json()[0] if bd_r.status_code == 200 and bd_r.json() else None

    # Submission
    sub_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_submissions",
        headers=headers,
        params={"session_id": f"eq.{session_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    submission = sub_r.json()[0] if sub_r.status_code == 200 and sub_r.json() else None

    # Documents
    doc_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_documents",
        headers=headers,
        params={"session_id": f"eq.{session_id}", "select": "*"},
        timeout=20.0,
    )
    documents = doc_r.json() if doc_r.status_code == 200 else []

    # Quiz results
    qr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_quiz_results",
        headers=headers,
        params={"session_id": f"eq.{session_id}", "select": "*"},
        timeout=20.0,
    )
    quiz_results = qr.json() if qr.status_code == 200 else []

    return {
        "session": session,
        "profile": prof,
        "personal_details": personal,
        "bank_details": bank,
        "submission": submission,
        "documents": documents,
        "quiz_results": quiz_results,
    }


# ── AI Chat endpoint for HAWK Guide ──────────────────────────────────────

class ChatBody(BaseModel):
    messages: list[dict[str, str]]
    step: int
    context: dict[str, Any] | None = None


@router.post("/chat")
def onboarding_chat(body: ChatBody, uid: str = Depends(require_supabase_uid)):
    """AI chat for the HAWK Guide onboarding assistant."""
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI not configured")

    prof = _get_profile(uid)
    name = prof.get("full_name", "there") if prof else "there"
    role = prof.get("role", "team member") if prof else "team member"
    role_type = prof.get("role_type", "closer") if prof else "closer"

    system_prompt = _build_onboarding_system_prompt(name, role, role_type, body.step, body.context or {})

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(body.messages)

    model = (OPENAI_MODEL or "gpt-4o").strip() or "gpt-4o"
    r = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1500,
        temperature=0.7,
    )

    return {
        "reply": (r.choices[0].message.content or "").strip(),
    }


def _build_onboarding_system_prompt(
    name: str, role: str, role_type: str, step: int, context: dict[str, Any]
) -> str:
    return f"""You are HAWK Guide, the AI onboarding assistant for Hawk Security's CRM.
You are guiding {name} (role: {role}, type: {role_type}) through their onboarding process.

Current step: {step}
Context: {context}

IMPORTANT RULES:
- Be warm, professional, and encouraging
- Keep responses concise but thorough
- Guide them through one thing at a time
- Validate their inputs helpfully
- If they seem confused, explain clearly
- Never reveal internal system details or database structure
- Always address them by name

STEP GUIDE:
Step 1 - Welcome: Greet them by name, explain the onboarding process has several steps (personal info, ID verification, bank details, document signing, product training). Tell them they cannot access the CRM until all steps are complete and approved.

Step 2 - Personal Details: Collect phone, WhatsApp, address, country, date of birth, emergency contact name and phone. Validate each field. Confirm when all fields are collected.

Step 3 - Government ID: Ask them to upload a clear photo of their government-issued ID (passport, driver's license, national ID). Accept JPG, PNG, or PDF. Confirm upload success.

Step 4 - Bank Details: Collect full name on account, bank name, account number, routing/SWIFT code, preferred payment method, and any notes. Validate each.

Step 5 - Document Review & Signing: Present each document (Contract, NDA, Acceptable Use Policy) one at a time. Explain what each document covers. After they read it, prompt them to sign using the signature pad.

Step 6 - Product Knowledge: Walk them through learning modules conversationally. After each module, give a short quiz (3-5 questions). They need to pass to continue. Be encouraging if they fail — let them retry.

Step 7 - Submission: Congratulate them. Tell them their onboarding is submitted for review and they'll be notified when approved.

Respond naturally in the conversation. If the user asks questions outside the current step, briefly answer but redirect back to the current task."""
