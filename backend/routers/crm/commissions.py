"""CRM Commissions router — track closing and residual commissions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, get_current_crm_user, require_role
from backend.database import get_db
from backend.models.crm_commission import CRMCommission
from backend.models.crm_user import CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES
from backend.schemas.crm_commission import CRMCommissionCreate, CRMCommissionOut

router = APIRouter(prefix="/commissions")


def _build_out(c: CRMCommission) -> CRMCommissionOut:
    return CRMCommissionOut(
        id=c.id,
        crm_user_id=c.crm_user_id,
        client_id=c.client_id,
        commission_type=c.commission_type,
        amount=c.amount,
        period_start=c.period_start,
        period_end=c.period_end,
        paid=c.paid,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("/my", response_model=List[CRMCommissionOut])
def my_commissions(
    paid: Optional[bool] = Query(None),
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    q = db.query(CRMCommission).filter(CRMCommission.crm_user_id == ctx.crm_user_id)
    if paid is not None:
        q = q.filter(CRMCommission.paid == paid)
    items = q.order_by(CRMCommission.created_at.desc()).all()
    return [_build_out(c) for c in items]


@router.get("/", response_model=List[CRMCommissionOut])
def list_commissions(
    crm_user_id: Optional[str] = Query(None),
    paid: Optional[bool] = Query(None),
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    q = db.query(CRMCommission)
    if crm_user_id:
        q = q.filter(CRMCommission.crm_user_id == crm_user_id)
    if paid is not None:
        q = q.filter(CRMCommission.paid == paid)
    items = q.order_by(CRMCommission.created_at.desc()).all()
    return [_build_out(c) for c in items]


@router.post("/", response_model=CRMCommissionOut)
def create_commission(
    body: CRMCommissionCreate,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    c = CRMCommission(
        id=str(uuid4()),
        crm_user_id=body.crm_user_id,
        client_id=body.client_id,
        commission_type=body.commission_type,
        amount=body.amount,
        period_start=body.period_start,
        period_end=body.period_end,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _build_out(c)


@router.put("/{commission_id}/pay", response_model=CRMCommissionOut)
def mark_paid(
    commission_id: str,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO)),
    db: Session = Depends(get_db),
):
    c = db.query(CRMCommission).filter(CRMCommission.id == commission_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Commission not found")
    c.paid = True
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return _build_out(c)
