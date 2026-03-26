"""
CRM Users Router
Handles user invites (Supabase auth), status updates, and performance reporting.
All operations require service role — not safe for frontend direct access.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.services.supabase_crm import (
    supabase_available,
    get_supabase,
    write_audit_log,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/users", tags=["crm-users"])

VALID_ROLES = ["rep", "team_lead", "hos", "ceo", "charlotte"]
VALID_STATUSES = ["active", "inactive", "on_leave"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_year() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ─── Models ───────────────────────────────────────────────────────────────────

class InviteUserRequest(BaseModel):
    email: str
    role: str
    team_lead_id: Optional[str] = None
    full_name: Optional[str] = None


class UpdateUserStatusRequest(BaseModel):
    status: str
    reason: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/invite")
async def invite_user(body: InviteUserRequest):
    """
    Invite a new user to the CRM.
    - Sends a Supabase magic-link invite email.
    - Creates the user record in the public.users table with role.
    HoS/CEO only (enforce via RLS or middleware in production).
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role. Must be one of: {VALID_ROLES}",
        )
    if not body.email or "@" not in body.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Valid email is required",
        )
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()

    # Check if user already exists
    existing = sb.table("users").select("id").eq("email", body.email).limit(1).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email {body.email} already exists",
        )

    # Send Supabase auth invite — creates auth.users record and sends magic link
    try:
        invite_res = sb.auth.admin.invite_user_by_email(
            body.email,
            options={"data": {"role": body.role, "full_name": body.full_name or ""}},
        )
        auth_user_id = invite_res.user.id if invite_res.user else None
    except Exception as exc:
        logger.error("Supabase auth invite failed for %s: %s", body.email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send invite: {exc}",
        ) from exc

    if not auth_user_id:
        raise HTTPException(status_code=500, detail="Invite created but no user ID returned")

    # Create public.users profile record
    user_data = {
        "id": auth_user_id,
        "email": body.email,
        "role": body.role,
        "full_name": body.full_name or "",
        "team_lead_id": body.team_lead_id,
        "status": "active",
        "daily_call_target": 30,
        "daily_loom_target": 5,
        "daily_scan_target": 10,
    }
    user_res = sb.table("users").insert(user_data).execute()
    if not user_res.data:
        logger.error("Auth invite succeeded but public.users insert failed for %s", body.email)
        # Auth user was created — return partial success with warning
        return {
            "id": auth_user_id,
            "email": body.email,
            "role": body.role,
            "status": "active",
            "invited": True,
            "warning": "User profile creation failed — they may need to complete onboarding",
        }

    write_audit_log({
        "action": "user_invited",
        "record_type": "user",
        "record_id": auth_user_id,
        "new_value": {"email": body.email, "role": body.role},
    })
    logger.info("Invited user %s with role %s", body.email, body.role)

    return {**user_res.data[0], "invited": True}


@router.put("/{user_id}/status")
async def update_user_status(user_id: str, body: UpdateUserStatusRequest):
    """Update a user's active status. HoS/CEO only."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {VALID_STATUSES}",
        )
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()
    res = sb.table("users").update({
        "status": body.status,
        "updated_at": _now(),
    }).eq("id", user_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="User not found")

    write_audit_log({
        "action": "user_status_changed",
        "record_type": "user",
        "record_id": user_id,
        "new_value": {"status": body.status, "reason": body.reason},
    })

    return {"id": user_id, "status": body.status}


@router.get("/{user_id}/performance")
async def get_user_performance(
    user_id: str,
    month_year: Optional[str] = None,
):
    """Get a rep's performance metrics for a given month."""
    if not supabase_available():
        return _empty_performance(user_id, month_year)

    target_month = month_year or _month_year()
    # Build date range for the month
    year, month = (int(x) for x in target_month.split("-"))
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    start = f"{year:04d}-{month:02d}-01T00:00:00+00:00"
    end = f"{next_year:04d}-{next_month:02d}-01T00:00:00+00:00"

    try:
        sb = get_supabase()

        # Calls made this month
        calls_res = (
            sb.table("activities")
            .select("id", count="exact")
            .eq("created_by", user_id)
            .eq("type", "call")
            .gte("created_at", start)
            .lt("created_at", end)
            .execute()
        )

        # Looms (stage moved to loom_sent)
        looms_res = (
            sb.table("activities")
            .select("id", count="exact")
            .eq("created_by", user_id)
            .eq("type", "stage_changed")
            .eq("metadata->>to_stage", "loom_sent")
            .gte("created_at", start)
            .lt("created_at", end)
            .execute()
        )

        # Scans run
        scans_res = (
            sb.table("activities")
            .select("id", count="exact")
            .eq("created_by", user_id)
            .eq("type", "scan_run")
            .gte("created_at", start)
            .lt("created_at", end)
            .execute()
        )

        # Closes and MRR
        closes_res = (
            sb.table("clients")
            .select("id, mrr")
            .eq("closing_rep_id", user_id)
            .gte("close_date", start)
            .lt("close_date", end)
            .execute()
        )
        closes = closes_res.data or []
        mrr_closed = sum(c.get("mrr", 0) for c in closes)

        # Commission earned
        comm_res = (
            sb.table("commissions")
            .select("amount")
            .eq("rep_id", user_id)
            .eq("month_year", target_month)
            .execute()
        )
        commission_earned = sum(c.get("amount", 0) for c in (comm_res.data or []))

        # Days since last close
        last_close_res = (
            sb.table("clients")
            .select("close_date")
            .eq("closing_rep_id", user_id)
            .order("close_date", desc=True)
            .limit(1)
            .execute()
        )
        days_since_last_close = None
        if last_close_res.data:
            last_close_str = last_close_res.data[0].get("close_date", "")
            if last_close_str:
                try:
                    last_close = datetime.fromisoformat(last_close_str.replace("Z", "+00:00"))
                    days_since_last_close = (datetime.now(timezone.utc) - last_close).days
                except (ValueError, TypeError):
                    pass

        at_risk = days_since_last_close is not None and days_since_last_close > 14

        return {
            "user_id": user_id,
            "month_year": target_month,
            "calls_made": calls_res.count or 0,
            "looms_sent": looms_res.count or 0,
            "scans_run": scans_res.count or 0,
            "closes": len(closes),
            "mrr_closed": round(mrr_closed, 2),
            "commission_earned": round(commission_earned, 2),
            "days_since_last_close": days_since_last_close,
            "at_risk": at_risk,
        }

    except Exception as exc:
        logger.error("get_user_performance error for %s: %s", user_id, exc)
        return _empty_performance(user_id, target_month)


def _empty_performance(user_id: str, month_year: Optional[str]) -> dict:
    return {
        "user_id": user_id,
        "month_year": month_year or _month_year(),
        "calls_made": 0,
        "looms_sent": 0,
        "scans_run": 0,
        "closes": 0,
        "mrr_closed": 0.0,
        "commission_earned": 0.0,
        "days_since_last_close": None,
        "at_risk": False,
    }
