"""CRM Activities router — log and list interactions on prospects."""
from __future__ import annotations

from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, get_current_crm_user, get_visible_prospects_query
from backend.database import get_db
from backend.models.crm_activity import CRMActivity
from backend.models.crm_prospect import CRMProspect
from backend.schemas.crm_activity import CRMActivityCreate, CRMActivityOut

router = APIRouter(prefix="/activities")


def _build_out(a: CRMActivity) -> CRMActivityOut:
    user_name = None
    if a.crm_user and a.crm_user.user:
        u = a.crm_user.user
        user_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email
    return CRMActivityOut(
        id=a.id,
        prospect_id=a.prospect_id,
        crm_user_id=a.crm_user_id,
        crm_user_name=user_name,
        activity_type=a.activity_type,
        description=a.description,
        old_stage=a.old_stage,
        new_stage=a.new_stage,
        created_at=a.created_at,
    )


@router.get("/prospect/{prospect_id}", response_model=List[CRMActivityOut])
def list_activities_for_prospect(
    prospect_id: str,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    # Verify visibility
    q = get_visible_prospects_query(ctx, db)
    p = q.filter(CRMProspect.id == prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")

    activities = db.query(CRMActivity).filter(
        CRMActivity.prospect_id == prospect_id
    ).order_by(CRMActivity.created_at.desc()).all()
    return [_build_out(a) for a in activities]


@router.post("/", response_model=CRMActivityOut, status_code=status.HTTP_201_CREATED)
def log_activity(
    body: CRMActivityCreate,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    # Verify visibility
    q = get_visible_prospects_query(ctx, db)
    p = q.filter(CRMProspect.id == body.prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")

    a = CRMActivity(
        id=str(uuid4()),
        prospect_id=body.prospect_id,
        crm_user_id=ctx.crm_user_id,
        activity_type=body.activity_type,
        description=body.description,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _build_out(a)
