"""CRM Clients router — manage converted (closed-won) clients."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, get_current_crm_user, require_role
from backend.database import get_db
from backend.models.crm_client import CRMClient, CLIENT_STATUS_CHURNED
from backend.models.crm_user import CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD
from backend.schemas.crm_client import CRMClientUpdate, CRMClientChurn, CRMClientOut

router = APIRouter(prefix="/clients")


def _build_out(c: CRMClient) -> CRMClientOut:
    rep_name = None
    if c.closed_by_rep and c.closed_by_rep.user:
        u = c.closed_by_rep.user
        rep_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email
    return CRMClientOut(
        id=c.id,
        prospect_id=c.prospect_id,
        company_name=c.company_name,
        domain=c.domain,
        contact_name=c.contact_name,
        contact_email=c.contact_email,
        mrr=c.mrr,
        closed_by_rep_id=c.closed_by_rep_id,
        closed_by_rep_name=rep_name,
        closed_at=c.closed_at,
        churn_risk=c.churn_risk,
        churn_risk_reason=c.churn_risk_reason,
        status=c.status,
        churned_at=c.churned_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("/", response_model=List[CRMClientOut])
def list_clients(
    status: Optional[str] = Query(None),
    churn_risk: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    q = db.query(CRMClient)

    # Filter by visibility (rep sees only clients they closed)
    if not ctx.has_full_visibility() and not ctx.is_team_lead():
        q = q.filter(CRMClient.closed_by_rep_id == ctx.crm_user_id)

    if status:
        q = q.filter(CRMClient.status == status)
    if churn_risk:
        q = q.filter(CRMClient.churn_risk == churn_risk)
    if search:
        q = q.filter(CRMClient.company_name.ilike(f"%{search}%"))

    items = q.order_by(CRMClient.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return [_build_out(c) for c in items]


@router.get("/{client_id}", response_model=CRMClientOut)
def get_client(
    client_id: str,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    c = db.query(CRMClient).filter(CRMClient.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    if not ctx.has_full_visibility() and not ctx.is_team_lead():
        if c.closed_by_rep_id != ctx.crm_user_id:
            raise HTTPException(status_code=403, detail="Access denied")
    return _build_out(c)


@router.put("/{client_id}", response_model=CRMClientOut)
def update_client(
    client_id: str,
    body: CRMClientUpdate,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD)),
    db: Session = Depends(get_db),
):
    c = db.query(CRMClient).filter(CRMClient.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(c, field, val)
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return _build_out(c)


@router.post("/{client_id}/churn", response_model=CRMClientOut)
def mark_churned(
    client_id: str,
    body: CRMClientChurn,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    c = db.query(CRMClient).filter(CRMClient.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    c.status = CLIENT_STATUS_CHURNED
    c.churned_at = datetime.now(timezone.utc)
    if body.reason:
        c.churn_risk_reason = body.reason
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return _build_out(c)
