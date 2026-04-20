"""CRM — VA Manager queue, assignments, outreach log, invite.

Routes surfaced here:
- GET  /api/crm/va/queue      — prospects in pipeline_status=va_queue (with filters)
- POST /api/crm/va/assign     — bulk-assign N prospects to a VA
- POST /api/crm/va/status     — update assignment status + optional outreach log row
- POST /api/crm/va/invite     — Supabase invite with role_type=va_outreach
- GET  /api/crm/va/team       — VA roster with today's assigned / reached_out / booked counts
- GET  /api/crm/va/my-queue   — the current VA's own assignments (+ ARIA-drafted email)

Access:
- CEO / VA manager: all endpoints.
- VA outreach: only `/my-queue` + `/status` (for assignments they own).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from config import CRM_PUBLIC_BASE_URL, SUPABASE_URL
from routers.crm_auth import require_supabase_uid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/va", tags=["crm-va"])

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _profile(uid: str) -> dict[str, Any] | None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "id,role,role_type,full_name,email", "limit": "1"},
        timeout=15.0,
    )
    r.raise_for_status()
    rows = r.json() or []
    return rows[0] if rows else None


def _require_manager_or_ceo(uid: str) -> dict[str, Any]:
    p = _profile(uid)
    if not p:
        raise HTTPException(status_code=403, detail="Profile not found")
    role = str(p.get("role") or "").lower()
    role_type = str(p.get("role_type") or "").lower()
    if role in ("ceo", "hos") or role_type == "va_manager":
        return p
    raise HTTPException(status_code=403, detail="CEO / HoS / VA manager only")


def _require_va(uid: str) -> dict[str, Any]:
    p = _profile(uid)
    if not p:
        raise HTTPException(status_code=403, detail="Profile not found")
    role_type = str(p.get("role_type") or "").lower()
    if role_type in ("va_outreach", "va_manager") or str(p.get("role") or "").lower() in ("ceo", "hos"):
        return p
    raise HTTPException(status_code=403, detail="VA role required")


# ─── Queue ────────────────────────────────────────────────────────────────


@router.get("/queue")
def list_queue(
    uid: str = Depends(require_supabase_uid),
    vertical: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_age_hours: int | None = Query(default=None, ge=0),
    assigned: bool = Query(default=False, description="Include rows already in va_assignments"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    """Prospects currently sitting in `pipeline_status=va_queue`.

    Defaults to unassigned rows (those not yet in `va_assignments`) so the
    queue reflects what's still available for bulk-assign.
    """
    _require_manager_or_ceo(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    params: dict[str, str] = {
        "select": (
            "id,domain,company_name,contact_name,contact_email,contact_phone,"
            "contact_linkedin_url,contact_title,email_subject,email_body,"
            "hawk_score,industry,city,province,stage,pipeline_status,"
            "vulnerability_found,created_at,last_activity_at"
        ),
        "pipeline_status": "eq.va_queue",
        "order": "hawk_score.desc.nullslast,last_activity_at.asc",
        "limit": str(limit),
    }
    if vertical:
        params["industry"] = f"eq.{vertical}"
    if min_score is not None:
        params["hawk_score"] = f"gte.{min_score}"

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects", headers=_sb_headers(), params=params, timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json() or []

    # Optionally filter out prospects that already have an assignment row.
    if not assigned and rows:
        ids = [str(p["id"]) for p in rows if p.get("id")]
        a = httpx.get(
            f"{SUPABASE_URL}/rest/v1/va_assignments",
            headers=_sb_headers(),
            params={"select": "prospect_id", "prospect_id": f"in.({','.join(ids)})", "limit": str(len(ids))},
            timeout=20.0,
        )
        a.raise_for_status()
        assigned_ids = {row["prospect_id"] for row in (a.json() or [])}
        rows = [p for p in rows if str(p.get("id")) not in assigned_ids]

    if max_age_hours is not None and rows:
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_hours * 3600
        rows = [
            p for p in rows
            if p.get("created_at") and datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).timestamp() >= cutoff
        ]

    return {"ok": True, "count": len(rows), "prospects": rows}


# ─── Assign ───────────────────────────────────────────────────────────────


class AssignBody(BaseModel):
    prospect_ids: list[str] = Field(..., min_length=1, max_length=500)
    va_id: str = Field(..., min_length=10)


@router.post("/assign")
def assign(body: AssignBody, uid: str = Depends(require_supabase_uid)) -> dict[str, Any]:
    """Bulk-assign prospects to a VA. Upserts `va_assignments` rows."""
    caller = _require_manager_or_ceo(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "prospect_id": pid,
            "assigned_va_id": body.va_id,
            "assigned_by": caller.get("id"),
            "assigned_at": now_iso,
            "status": "assigned",
            "last_activity_at": now_iso,
        }
        for pid in body.prospect_ids
    ]
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/va_assignments",
        headers={**_sb_headers(), "Prefer": "return=representation,resolution=merge-duplicates"},
        params={"on_conflict": "prospect_id"},
        json=rows,
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("va.assign failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=400, detail=r.text[:500])

    # Mirror assignment onto prospects.assigned_rep_id so existing RLS / UI
    # "Assigned to" columns continue to work without changes.
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={"id": f"in.({','.join(body.prospect_ids)})"},
        json={"assigned_rep_id": body.va_id, "last_activity_at": now_iso},
        timeout=30.0,
    )

    return {"ok": True, "assigned": len(body.prospect_ids), "va_id": body.va_id}


# ─── Status update ────────────────────────────────────────────────────────


class StatusBody(BaseModel):
    assignment_id: str = Field(..., min_length=10)
    status: Literal[
        "assigned", "in_progress", "reached_out", "call_booked",
        "no_answer", "not_interested", "closed_lost", "closed_won",
    ]
    notes: str | None = None
    log_outreach: bool = Field(
        default=False,
        description="If true, also append a va_outreach_log row (channel=email, outcome=<status>).",
    )
    channel: Literal["email", "phone", "linkedin", "sms", "other"] = "email"


@router.post("/status")
def update_status(body: StatusBody, uid: str = Depends(require_supabase_uid)) -> dict[str, Any]:
    """Update a VA assignment's status and optionally append an outreach-log row."""
    caller = _require_va(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    now_iso = datetime.now(timezone.utc).isoformat()
    patch = {"status": body.status, "last_activity_at": now_iso}
    if body.notes is not None:
        patch["notes"] = body.notes

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/va_assignments",
        headers=_sb_headers(),
        params={"id": f"eq.{body.assignment_id}"},
        json=patch,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])

    # Outreach log row for audit
    outcome_map = {
        "reached_out": "sent",
        "call_booked": "call_booked",
        "no_answer": "no_answer",
        "not_interested": "not_interested",
        "closed_lost": "not_interested",
        "closed_won": "call_booked",
        "in_progress": "note",
        "assigned": "note",
    }
    if body.log_outreach:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/va_outreach_log",
            headers=_sb_headers(),
            json={
                "assignment_id": body.assignment_id,
                "va_id": caller.get("id"),
                "channel": body.channel,
                "outcome": outcome_map.get(body.status, "note"),
                "notes": body.notes,
                "logged_at": now_iso,
            },
            timeout=15.0,
        )

    # Mirror terminal statuses onto prospects.stage so the pipeline board stays truthful.
    stage_map = {
        "call_booked": "call_booked",
        "closed_won": "closed_won",
        "closed_lost": "lost",
        "not_interested": "lost",
    }
    if body.status in stage_map:
        asg = httpx.get(
            f"{SUPABASE_URL}/rest/v1/va_assignments",
            headers=_sb_headers(),
            params={"id": f"eq.{body.assignment_id}", "select": "prospect_id", "limit": "1"},
            timeout=15.0,
        )
        asg.raise_for_status()
        rows = asg.json() or []
        if rows:
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
                params={"id": f"eq.{rows[0]['prospect_id']}"},
                json={"stage": stage_map[body.status], "last_activity_at": now_iso},
                timeout=15.0,
            )

    return {"ok": True}


# ─── Team + My Queue ──────────────────────────────────────────────────────


@router.get("/team")
def team(uid: str = Depends(require_supabase_uid)) -> dict[str, Any]:
    """VA roster with today's assigned / reached_out / booked counts."""
    _require_manager_or_ceo(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    profiles = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={
            "select": "id,full_name,email,role_type,status",
            "role_type": "in.(va_outreach,va_manager)",
            "order": "full_name.asc",
            "limit": "500",
        },
        timeout=15.0,
    )
    profiles.raise_for_status()
    vas = profiles.json() or []

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    rows: list[dict[str, Any]] = []
    for v in vas:
        vid = v["id"]
        assigned_r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/va_assignments",
            headers={**_sb_headers(), "Prefer": "count=exact"},
            params={
                "select": "id",
                "assigned_va_id": f"eq.{vid}",
                "assigned_at": f"gte.{today_start}",
                "limit": "1",
            },
            timeout=15.0,
        )
        assigned_count = int((assigned_r.headers.get("content-range") or "/0").split("/", 1)[1])

        reached_r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/va_outreach_log",
            headers={**_sb_headers(), "Prefer": "count=exact"},
            params={
                "select": "id",
                "va_id": f"eq.{vid}",
                "outcome": "eq.sent",
                "logged_at": f"gte.{today_start}",
                "limit": "1",
            },
            timeout=15.0,
        )
        reached_count = int((reached_r.headers.get("content-range") or "/0").split("/", 1)[1])

        booked_r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/va_outreach_log",
            headers={**_sb_headers(), "Prefer": "count=exact"},
            params={
                "select": "id",
                "va_id": f"eq.{vid}",
                "outcome": "eq.call_booked",
                "logged_at": f"gte.{today_start}",
                "limit": "1",
            },
            timeout=15.0,
        )
        booked_count = int((booked_r.headers.get("content-range") or "/0").split("/", 1)[1])

        rows.append({
            **v,
            "today_assigned": assigned_count,
            "today_reached_out": reached_count,
            "today_booked": booked_count,
        })

    return {"ok": True, "count": len(rows), "vas": rows}


@router.get("/my-queue")
def my_queue(uid: str = Depends(require_supabase_uid), limit: int = Query(default=200, ge=1, le=500)) -> dict[str, Any]:
    """The current VA's open assignments with the ARIA-drafted email ready to copy."""
    _require_va(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    a = httpx.get(
        f"{SUPABASE_URL}/rest/v1/va_assignments",
        headers=_sb_headers(),
        params={
            "select": (
                "id,prospect_id,assigned_va_id,assigned_by,assigned_at,status,notes,last_activity_at,"
                "prospect:prospect_id(id,domain,company_name,contact_name,contact_email,"
                "contact_phone,contact_linkedin_url,contact_title,email_subject,email_body,"
                "hawk_score,industry,city,province,stage,vulnerability_found)"
            ),
            "assigned_va_id": f"eq.{uid}",
            "status": "in.(assigned,in_progress,reached_out,no_answer)",
            "order": "assigned_at.desc",
            "limit": str(limit),
        },
        timeout=20.0,
    )
    a.raise_for_status()
    return {"ok": True, "assignments": a.json() or []}


# ─── Invite ───────────────────────────────────────────────────────────────


class VAInviteBody(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    role_type: Literal["va_outreach", "va_manager"] = "va_outreach"


@router.post("/invite")
def invite_va(body: VAInviteBody, uid: str = Depends(require_supabase_uid)) -> dict[str, Any]:
    """Invite a VA via Supabase auth. Creates profile with role_type=va_outreach."""
    _require_manager_or_ceo(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    meta = {
        "full_name": body.full_name.strip(),
        "crm_role": "closer",  # sales seat (required by onboarding); role_type is the VA marker
        "crm_role_type": body.role_type,
        "crm_initial_status": "invited",
    }
    redir = f"{CRM_PUBLIC_BASE_URL}/onboarding" if CRM_PUBLIC_BASE_URL else None
    payload: dict[str, Any] = {"email": body.email.lower().strip(), "data": meta}
    if redir:
        payload["options"] = {"email_redirect_to": redir}

    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/invite",
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("va.invite failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=400, detail=r.text[:500])

    return {"ok": True, "message": f"Invite sent to {body.email}"}
