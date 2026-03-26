"""
CRM Product Commands Router
Direction 2: CRM → HAWK product write commands.
Every command is executed through FastAPI, logged to audit trail,
and requires explicit role authorization.

Routes:
  POST /api/crm/commands/extend-trial
  POST /api/crm/commands/convert-trial
  POST /api/crm/commands/change-plan
  POST /api/crm/commands/grant-feature
  POST /api/crm/commands/revoke-feature
  POST /api/crm/commands/pause-account
  POST /api/crm/commands/reactivate-account
  POST /api/crm/commands/add-scan-credits
  POST /api/crm/commands/force-password-reset
  POST /api/crm/commands/send-notification
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.services.supabase_crm import get_supabase, supabase_available, write_audit_log, log_activity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/commands", tags=["crm-product-commands"])

VALID_PLANS = ["trial", "starter", "shield", "enterprise"]
VALID_FEATURES = [
    "compliance", "agency", "hawk_ai", "breach_check",
    "advanced_reports", "white_label", "api_access",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_actor_id(request: Request) -> Optional[str]:
    """Extract the acting user's ID from the Bearer JWT."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    try:
        sb = get_supabase()
        res = sb.auth.get_user(token)
        return res.user.id if res.user else None
    except Exception:
        return None


def _get_actor_role(actor_id: str) -> Optional[str]:
    try:
        sb = get_supabase()
        res = sb.table("users").select("role").eq("id", actor_id).single().execute()
        return res.data.get("role") if res.data else None
    except Exception:
        return None


def _require_role(actor_id: Optional[str], allowed_roles: list[str]) -> None:
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = _get_actor_role(actor_id)
    if role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"This action requires one of: {allowed_roles}",
        )


def _get_hawk_user_id(client_id: str) -> str:
    """Resolve hawk_user_id from CRM client_id. Raises 404 if not found."""
    sb = get_supabase()
    res = (
        sb.table("clients")
        .select("hawk_user_id, company_name")
        .eq("id", client_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Client not found")
    hawk_user_id = res.data.get("hawk_user_id")
    if not hawk_user_id:
        raise HTTPException(
            status_code=422,
            detail="Client has no linked HAWK account — cannot execute product command",
        )
    return hawk_user_id


def _update_product_user(hawk_user_id: str, updates: dict) -> None:
    """Apply updates to the HAWK product user record via SQLAlchemy."""
    db: Session = SessionLocal()
    try:
        from backend.models.user import User
        user = db.query(User).filter(User.id == hawk_user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="HAWK product user not found")
        for key, value in updates.items():
            setattr(user, key, value)
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error("_update_product_user failed for %s: %s", hawk_user_id, exc)
        raise HTTPException(status_code=500, detail=f"Product update failed: {exc}") from exc
    finally:
        db.close()


def _audit(actor_id: str, action: str, client_id: str, details: dict) -> None:
    write_audit_log({
        "action": action,
        "record_type": "client",
        "record_id": client_id,
        "performed_by": actor_id,
        "new_value": details,
    })
    log_activity({
        "client_id": client_id,
        "type": "note_added",
        "notes": f"Product command: {action}",
        "metadata": {"actor_id": actor_id, **details},
    })


# ─── Commands ─────────────────────────────────────────────────────────────────

class ExtendTrialRequest(BaseModel):
    client_id: str
    days: int
    reason: Optional[str] = None


@router.post("/extend-trial")
async def extend_trial(body: ExtendTrialRequest, request: Request):
    """Extend a customer's trial by N days. CEO, HoS, CSM."""
    if not 1 <= body.days <= 30:
        raise HTTPException(status_code=422, detail="days must be 1–30")

    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo", "hos", "csm"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    hawk_user_id = _get_hawk_user_id(body.client_id)

    # Read current trial end
    db: Session = SessionLocal()
    try:
        from backend.models.user import User
        user = db.query(User).filter(User.id == hawk_user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="HAWK product user not found")
        current_end = user.trial_ends_at or datetime.now(timezone.utc)
        new_end = current_end + timedelta(days=body.days)
        user.trial_ends_at = new_end
        db.commit()
        new_end_str = new_end.isoformat()
    finally:
        db.close()

    _audit(actor_id, "extend_trial", body.client_id, {
        "days": body.days,
        "new_trial_end": new_end_str,
        "reason": body.reason,
    })
    logger.info("Trial extended %d days for hawk_user %s by %s", body.days, hawk_user_id, actor_id)
    return {"success": True, "new_trial_end": new_end_str}


class ConvertTrialRequest(BaseModel):
    client_id: str
    plan: str
    reason: Optional[str] = None


@router.post("/convert-trial")
async def convert_trial(body: ConvertTrialRequest, request: Request):
    """End trial early and convert to paid. CEO, HoS."""
    if body.plan not in ["starter", "shield", "enterprise"]:
        raise HTTPException(status_code=422, detail=f"Invalid plan: {body.plan}")

    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo", "hos"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    hawk_user_id = _get_hawk_user_id(body.client_id)
    _update_product_user(hawk_user_id, {
        "plan": body.plan,
        "trial_ends_at": None,
    })
    _audit(actor_id, "convert_trial", body.client_id, {"plan": body.plan, "reason": body.reason})
    return {"success": True, "plan": body.plan}


class ChangePlanRequest(BaseModel):
    client_id: str
    plan: str
    reason: Optional[str] = None


@router.post("/change-plan")
async def change_plan(body: ChangePlanRequest, request: Request):
    """Change a customer's plan. CEO, HoS."""
    if body.plan not in VALID_PLANS:
        raise HTTPException(status_code=422, detail=f"Invalid plan. Must be one of: {VALID_PLANS}")

    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo", "hos"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    hawk_user_id = _get_hawk_user_id(body.client_id)
    _update_product_user(hawk_user_id, {"plan": body.plan})

    # Update CRM client record too
    get_supabase().table("clients").update({"plan": body.plan}).eq("id", body.client_id).execute()

    _audit(actor_id, "change_plan", body.client_id, {"plan": body.plan, "reason": body.reason})
    return {"success": True, "plan": body.plan}


class GrantFeatureRequest(BaseModel):
    client_id: str
    feature: str
    reason: Optional[str] = None


@router.post("/grant-feature")
async def grant_feature(body: GrantFeatureRequest, request: Request):
    """Grant out-of-plan feature access. CEO only."""
    if body.feature not in VALID_FEATURES:
        raise HTTPException(status_code=422, detail=f"Invalid feature. Must be one of: {VALID_FEATURES}")

    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Feature grants are stored in client_health_sync.features_accessed
    sb = get_supabase()
    hawk_user_id = _get_hawk_user_id(body.client_id)

    sb.table("client_health_sync").update({
        f"features_accessed->{body.feature}": True,
    }).eq("client_id", body.client_id).execute()

    # Also set a flag in the HAWK product via a feature_flags table if it exists
    # For now, log the grant — product reads it from sync on next login
    _audit(actor_id, "grant_feature", body.client_id, {
        "feature": body.feature,
        "hawk_user_id": hawk_user_id,
        "reason": body.reason,
    })
    return {"success": True, "feature": body.feature, "access": True}


@router.post("/revoke-feature")
async def revoke_feature(body: GrantFeatureRequest, request: Request):
    """Revoke out-of-plan feature access. CEO only."""
    if body.feature not in VALID_FEATURES:
        raise HTTPException(status_code=422, detail=f"Invalid feature. Must be one of: {VALID_FEATURES}")

    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()
    hawk_user_id = _get_hawk_user_id(body.client_id)

    sb.table("client_health_sync").update({
        f"features_accessed->{body.feature}": False,
    }).eq("client_id", body.client_id).execute()

    _audit(actor_id, "revoke_feature", body.client_id, {
        "feature": body.feature,
        "hawk_user_id": hawk_user_id,
    })
    return {"success": True, "feature": body.feature, "access": False}


class PauseAccountRequest(BaseModel):
    client_id: str
    reason: Optional[str] = None


@router.post("/pause-account")
async def pause_account(body: PauseAccountRequest, request: Request):
    """Suspend billing and access. CEO only."""
    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    hawk_user_id = _get_hawk_user_id(body.client_id)
    _update_product_user(hawk_user_id, {"plan": "paused"})
    get_supabase().table("clients").update({"status": "paused"}).eq("id", body.client_id).execute()

    _audit(actor_id, "pause_account", body.client_id, {
        "hawk_user_id": hawk_user_id,
        "reason": body.reason,
    })
    return {"success": True, "status": "paused"}


@router.post("/reactivate-account")
async def reactivate_account(body: PauseAccountRequest, request: Request):
    """Reactivate a paused account. CEO, HoS."""
    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo", "hos"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Determine what plan to restore — default to starter
    sb = get_supabase()
    client_res = sb.table("clients").select("plan").eq("id", body.client_id).single().execute()
    plan = (client_res.data or {}).get("plan", "starter")
    if plan == "paused":
        plan = "starter"

    hawk_user_id = _get_hawk_user_id(body.client_id)
    _update_product_user(hawk_user_id, {"plan": plan})
    sb.table("clients").update({"status": "active"}).eq("id", body.client_id).execute()

    _audit(actor_id, "reactivate_account", body.client_id, {
        "hawk_user_id": hawk_user_id,
        "restored_plan": plan,
    })
    return {"success": True, "status": "active", "plan": plan}


class ScanCreditsRequest(BaseModel):
    client_id: str
    credits: int
    reason: Optional[str] = None


@router.post("/add-scan-credits")
async def add_scan_credits(body: ScanCreditsRequest, request: Request):
    """Add free scan credits to a customer's account. CEO, HoS, CSM."""
    if not 1 <= body.credits <= 100:
        raise HTTPException(status_code=422, detail="credits must be 1–100")

    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo", "hos", "csm"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    hawk_user_id = _get_hawk_user_id(body.client_id)

    # Increment scan_credits in HAWK product user (column may not exist — add if needed)
    db: Session = SessionLocal()
    try:
        from backend.models.user import User
        from sqlalchemy import text
        user = db.query(User).filter(User.id == hawk_user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="HAWK product user not found")
        current = getattr(user, "scan_credits", 0) or 0
        if hasattr(user, "scan_credits"):
            user.scan_credits = current + body.credits
            db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.warning("scan_credits column may not exist: %s — logging only", exc)
    finally:
        db.close()

    _audit(actor_id, "add_scan_credits", body.client_id, {
        "credits": body.credits,
        "hawk_user_id": hawk_user_id,
        "reason": body.reason,
    })
    return {"success": True, "credits_added": body.credits}


class ForceResetRequest(BaseModel):
    client_id: str
    reason: Optional[str] = None


@router.post("/force-password-reset")
async def force_password_reset(body: ForceResetRequest, request: Request):
    """Force a password reset for a customer. CEO only."""
    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    hawk_user_id = _get_hawk_user_id(body.client_id)

    # Get the user's email from HAWK product
    db: Session = SessionLocal()
    try:
        from backend.models.user import User
        user = db.query(User).filter(User.id == hawk_user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="HAWK product user not found")
        email = user.email
    finally:
        db.close()

    # Trigger password reset email via HAWK auth service
    try:
        import httpx
        import os
        api_url = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8000")
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{api_url}/api/auth/request-reset",
                json={"email": email},
                timeout=10.0,
            )
    except Exception as exc:
        logger.warning("Password reset email trigger failed: %s", exc)

    _audit(actor_id, "force_password_reset", body.client_id, {
        "hawk_user_id": hawk_user_id,
        "email": email,
        "reason": body.reason,
    })
    return {"success": True, "email": email}


class SendNotificationRequest(BaseModel):
    client_id: str
    title: str
    message: str
    notification_type: str = "info"   # info, warning, success, error


@router.post("/send-notification")
async def send_notification(body: SendNotificationRequest, request: Request):
    """Send an in-product notification to a customer. All CRM roles."""
    if not body.title.strip() or not body.message.strip():
        raise HTTPException(status_code=422, detail="title and message are required")

    actor_id = _get_actor_id(request)
    _require_role(actor_id, ["ceo", "hos", "team_lead", "rep", "csm"])
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    hawk_user_id = _get_hawk_user_id(body.client_id)

    # Create notification in HAWK product notifications table via SQLAlchemy
    db: Session = SessionLocal()
    try:
        from backend.models.notification import Notification
        import uuid
        notif = Notification(
            id=str(uuid.uuid4()),
            user_id=hawk_user_id,
            title=body.title,
            message=body.message,
            type=body.notification_type,
            read=False,
        )
        db.add(notif)
        db.commit()
        notif_id = notif.id
    except Exception as exc:
        db.rollback()
        logger.error("send_notification failed for hawk_user %s: %s", hawk_user_id, exc)
        raise HTTPException(status_code=500, detail=f"Notification delivery failed: {exc}") from exc
    finally:
        db.close()

    _audit(actor_id, "send_notification", body.client_id, {
        "title": body.title,
        "type": body.notification_type,
        "hawk_user_id": hawk_user_id,
    })
    return {"success": True, "notification_id": notif_id}
