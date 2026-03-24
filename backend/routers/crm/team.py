"""CRM Team router — manage CRM users (reps, leads, admins)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import hash_password
from backend.auth_crm import CRMContext, get_current_crm_user, require_role
from backend.database import get_db
from backend.models import User
from backend.models.crm_user import CRMUser, CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD
from backend.models.crm_prospect import CRMProspect, STAGE_CLOSED_WON
from backend.models.crm_commission import CRMCommission
from backend.schemas.crm_team import CRMUserCreate, CRMUserUpdate, CRMUserOut, CRMUserStats

router = APIRouter(prefix="/team")

MANAGEMENT_ROLES = (CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)


def _build_user_out(crm_user: CRMUser, db: Session) -> CRMUserOut:
    user = crm_user.user
    return CRMUserOut(
        id=crm_user.id,
        user_id=crm_user.user_id,
        crm_role=crm_user.crm_role,
        monthly_target=crm_user.monthly_target,
        team_lead_id=crm_user.team_lead_id,
        is_active=crm_user.is_active,
        email=user.email if user else "",
        first_name=user.first_name if user else None,
        last_name=user.last_name if user else None,
        created_at=crm_user.created_at,
        updated_at=crm_user.updated_at,
    )


@router.get("/me", response_model=CRMUserOut)
def get_my_crm_profile(ctx: CRMContext = Depends(get_current_crm_user)):
    """Get the current user's CRM profile."""
    return _build_user_out(ctx.crm_user, None)


@router.get("/", response_model=List[CRMUserStats])
def list_crm_users(
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD)),
    db: Session = Depends(get_db),
):
    """List CRM users. Team leads see their own team only."""
    if ctx.is_team_lead():
        users = db.query(CRMUser).filter(
            CRMUser.team_lead_id == ctx.crm_user_id,
            CRMUser.is_active == True,  # noqa: E712
        ).all()
    else:
        users = db.query(CRMUser).filter(CRMUser.is_active == True).all()  # noqa: E712

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = []
    for cu in users:
        base = _build_user_out(cu, db)
        closes = db.query(CRMProspect).filter(
            CRMProspect.assigned_rep_id == cu.id,
            CRMProspect.stage == STAGE_CLOSED_WON,
            CRMProspect.updated_at >= month_start,
        ).count()
        commission = db.query(func.sum(CRMCommission.amount)).filter(
            CRMCommission.crm_user_id == cu.id,
            CRMCommission.created_at >= month_start,
        ).scalar() or 0
        prospects_total = db.query(CRMProspect).filter(
            CRMProspect.assigned_rep_id == cu.id,
        ).count()
        result.append(CRMUserStats(
            **base.model_dump(),
            closes_this_month=closes,
            commission_this_month=commission,
            total_prospects=prospects_total,
        ))
    return result


@router.post("/", response_model=CRMUserOut, status_code=status.HTTP_201_CREATED)
def create_crm_user(
    body: CRMUserCreate,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    """Create a new CRM user (creates underlying User account + CRMUser profile)."""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use")

    user_id = str(uuid4())
    new_user = User(
        id=user_id,
        email=body.email,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        plan="trial",
    )
    db.add(new_user)

    crm_id = str(uuid4())
    crm_user = CRMUser(
        id=crm_id,
        user_id=user_id,
        crm_role=body.crm_role,
        monthly_target=body.monthly_target,
        team_lead_id=body.team_lead_id,
    )
    db.add(crm_user)
    db.commit()
    db.refresh(crm_user)
    return _build_user_out(crm_user, db)


@router.get("/{crm_user_id}", response_model=CRMUserStats)
def get_crm_user(
    crm_user_id: str,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    """Get single CRM user detail. Team leads can only view own team."""
    cu = db.query(CRMUser).filter(CRMUser.id == crm_user_id).first()
    if not cu:
        raise HTTPException(status_code=404, detail="CRM user not found")

    if ctx.is_team_lead() and cu.team_lead_id != ctx.crm_user_id and cu.id != ctx.crm_user_id:
        raise HTTPException(status_code=403, detail="Not your team member")

    if not ctx.has_full_visibility() and not ctx.is_team_lead():
        if cu.id != ctx.crm_user_id:
            raise HTTPException(status_code=403, detail="Access denied")

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    base = _build_user_out(cu, db)
    closes = db.query(CRMProspect).filter(
        CRMProspect.assigned_rep_id == cu.id,
        CRMProspect.stage == STAGE_CLOSED_WON,
        CRMProspect.updated_at >= month_start,
    ).count()
    commission = db.query(func.sum(CRMCommission.amount)).filter(
        CRMCommission.crm_user_id == cu.id,
        CRMCommission.created_at >= month_start,
    ).scalar() or 0
    prospects_total = db.query(CRMProspect).filter(CRMProspect.assigned_rep_id == cu.id).count()

    return CRMUserStats(
        **base.model_dump(),
        closes_this_month=closes,
        commission_this_month=commission,
        total_prospects=prospects_total,
    )


@router.put("/{crm_user_id}", response_model=CRMUserOut)
def update_crm_user(
    crm_user_id: str,
    body: CRMUserUpdate,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    """Update CRM user role, target, or team assignment."""
    cu = db.query(CRMUser).filter(CRMUser.id == crm_user_id).first()
    if not cu:
        raise HTTPException(status_code=404, detail="CRM user not found")

    updated = cu
    if body.crm_role is not None:
        updated = CRMUser(
            id=cu.id, user_id=cu.user_id,
            crm_role=body.crm_role,
            monthly_target=body.monthly_target if body.monthly_target is not None else cu.monthly_target,
            team_lead_id=body.team_lead_id if body.team_lead_id is not None else cu.team_lead_id,
            is_active=body.is_active if body.is_active is not None else cu.is_active,
        )
        db.merge(updated)
    else:
        if body.monthly_target is not None:
            cu.monthly_target = body.monthly_target
        if body.team_lead_id is not None:
            cu.team_lead_id = body.team_lead_id
        if body.is_active is not None:
            cu.is_active = body.is_active

    if body.first_name is not None or body.last_name is not None:
        user = db.query(User).filter(User.id == cu.user_id).first()
        if user:
            if body.first_name is not None:
                user.first_name = body.first_name
            if body.last_name is not None:
                user.last_name = body.last_name

    db.commit()
    db.refresh(cu)
    return _build_user_out(cu, db)


@router.put("/{crm_user_id}/deactivate", response_model=CRMUserOut)
def deactivate_crm_user(
    crm_user_id: str,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    """Deactivate a CRM user."""
    cu = db.query(CRMUser).filter(CRMUser.id == crm_user_id).first()
    if not cu:
        raise HTTPException(status_code=404, detail="CRM user not found")
    cu.is_active = False
    db.commit()
    db.refresh(cu)
    return _build_user_out(cu, db)
