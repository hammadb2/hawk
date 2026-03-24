"""CRM Prospects router — full CRUD, stage management, CSV import."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, get_current_crm_user, require_role, get_visible_prospects_query
from backend.database import get_db
from backend.models.crm_user import CRMUser, CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD, CRM_ROLE_SALES_REP
from backend.models.crm_prospect import CRMProspect, PIPELINE_STAGES, STAGE_CLOSED_WON, STAGE_CLOSED_LOST
from backend.models.crm_activity import CRMActivity, ACTIVITY_STAGE_CHANGE, ACTIVITY_NOTE
from backend.models.crm_client import CRMClient
from backend.schemas.crm_prospect import (
    CRMProspectCreate, CRMProspectUpdate, CRMProspectStageUpdate, CRMProspectAssign, CRMProspectOut
)

router = APIRouter(prefix="/prospects")

EDIT_ROLES = (CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD, CRM_ROLE_SALES_REP)


def _build_out(p: CRMProspect, db: Session) -> CRMProspectOut:
    rep_name = None
    if p.assigned_rep and p.assigned_rep.user:
        u = p.assigned_rep.user
        rep_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email
    return CRMProspectOut(
        id=p.id,
        company_name=p.company_name,
        domain=p.domain,
        contact_name=p.contact_name,
        contact_email=p.contact_email,
        contact_phone=p.contact_phone,
        industry=p.industry,
        city=p.city,
        stage=p.stage,
        hawk_score=p.hawk_score,
        assigned_rep_id=p.assigned_rep_id,
        assigned_rep_name=rep_name,
        source=p.source,
        notes=p.notes,
        estimated_mrr=p.estimated_mrr,
        lost_reason=p.lost_reason,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/", response_model=List[CRMProspectOut])
def list_prospects(
    stage: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    assigned_rep_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    q = get_visible_prospects_query(ctx, db)
    if stage:
        q = q.filter(CRMProspect.stage == stage)
    if source:
        q = q.filter(CRMProspect.source == source)
    if assigned_rep_id:
        q = q.filter(CRMProspect.assigned_rep_id == assigned_rep_id)
    if search:
        like = f"%{search}%"
        q = q.filter(
            CRMProspect.company_name.ilike(like) | CRMProspect.domain.ilike(like)
        )
    total = q.count()
    items = q.order_by(CRMProspect.updated_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return [_build_out(p, db) for p in items]


@router.post("/", response_model=CRMProspectOut, status_code=status.HTTP_201_CREATED)
def create_prospect(
    body: CRMProspectCreate,
    ctx: CRMContext = Depends(require_role(*EDIT_ROLES)),
    db: Session = Depends(get_db),
):
    assigned_rep_id = body.assigned_rep_id or (
        ctx.crm_user_id if ctx.role == CRM_ROLE_SALES_REP else None
    )
    p = CRMProspect(
        id=str(uuid4()),
        company_name=body.company_name,
        domain=body.domain,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        industry=body.industry,
        city=body.city,
        source=body.source,
        notes=body.notes,
        estimated_mrr=body.estimated_mrr,
        assigned_rep_id=assigned_rep_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _build_out(p, db)


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_prospects_csv(
    file: UploadFile = File(...),
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    """Import prospects from CSV. Required columns: company_name. Optional: domain, contact_name, contact_email, contact_phone, industry, city."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if "company_name" not in (reader.fieldnames or []):
        raise HTTPException(status_code=400, detail="CSV must have a 'company_name' column")

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(reader):
        company_name = (row.get("company_name") or "").strip()
        if not company_name:
            errors.append({"row": i + 2, "error": "Missing company_name"})
            continue

        domain = (row.get("domain") or "").strip() or None
        # Skip duplicates by domain if provided
        if domain:
            existing = db.query(CRMProspect).filter(CRMProspect.domain == domain).first()
            if existing:
                skipped += 1
                continue

        p = CRMProspect(
            id=str(uuid4()),
            company_name=company_name,
            domain=domain,
            contact_name=(row.get("contact_name") or "").strip() or None,
            contact_email=(row.get("contact_email") or "").strip() or None,
            contact_phone=(row.get("contact_phone") or "").strip() or None,
            industry=(row.get("industry") or "").strip() or None,
            city=(row.get("city") or "").strip() or None,
            source="csv_import",
        )
        db.add(p)
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


@router.get("/{prospect_id}", response_model=CRMProspectOut)
def get_prospect(
    prospect_id: str,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    q = get_visible_prospects_query(ctx, db)
    p = q.filter(CRMProspect.id == prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return _build_out(p, db)


@router.put("/{prospect_id}", response_model=CRMProspectOut)
def update_prospect(
    prospect_id: str,
    body: CRMProspectUpdate,
    ctx: CRMContext = Depends(require_role(*EDIT_ROLES)),
    db: Session = Depends(get_db),
):
    q = get_visible_prospects_query(ctx, db)
    p = q.filter(CRMProspect.id == prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(p, field, val)
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)
    return _build_out(p, db)


@router.put("/{prospect_id}/stage", response_model=CRMProspectOut)
def move_stage(
    prospect_id: str,
    body: CRMProspectStageUpdate,
    ctx: CRMContext = Depends(require_role(*EDIT_ROLES)),
    db: Session = Depends(get_db),
):
    if body.stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {body.stage}")

    q = get_visible_prospects_query(ctx, db)
    p = q.filter(CRMProspect.id == prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")

    old_stage = p.stage
    p.stage = body.stage
    if body.stage == STAGE_CLOSED_LOST and body.lost_reason:
        p.lost_reason = body.lost_reason
    p.updated_at = datetime.now(timezone.utc)

    # Log stage change activity
    activity = CRMActivity(
        id=str(uuid4()),
        prospect_id=p.id,
        crm_user_id=ctx.crm_user_id,
        activity_type=ACTIVITY_STAGE_CHANGE,
        description=body.note,
        old_stage=old_stage,
        new_stage=body.stage,
    )
    db.add(activity)
    db.commit()
    db.refresh(p)
    return _build_out(p, db)


@router.put("/{prospect_id}/assign", response_model=CRMProspectOut)
def assign_prospect(
    prospect_id: str,
    body: CRMProspectAssign,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD)),
    db: Session = Depends(get_db),
):
    p = db.query(CRMProspect).filter(CRMProspect.id == prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")
    p.assigned_rep_id = body.assigned_rep_id
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)
    return _build_out(p, db)


@router.post("/{prospect_id}/convert", response_model=CRMProspectOut)
def convert_to_client(
    prospect_id: str,
    ctx: CRMContext = Depends(require_role(*EDIT_ROLES)),
    db: Session = Depends(get_db),
):
    """Convert a closed-won prospect to a client."""
    q = get_visible_prospects_query(ctx, db)
    p = q.filter(CRMProspect.id == prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")
    if p.stage != STAGE_CLOSED_WON:
        raise HTTPException(status_code=400, detail="Prospect must be in closed_won stage to convert")
    if p.client:
        raise HTTPException(status_code=400, detail="Prospect already converted to client")

    client = CRMClient(
        id=str(uuid4()),
        prospect_id=p.id,
        company_name=p.company_name,
        domain=p.domain,
        contact_name=p.contact_name,
        contact_email=p.contact_email,
        mrr=p.estimated_mrr or 99700,  # default $997 in cents
        closed_by_rep_id=p.assigned_rep_id,
        closed_at=datetime.now(timezone.utc),
    )
    db.add(client)
    db.commit()
    db.refresh(p)
    return _build_out(p, db)


@router.delete("/{prospect_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prospect(
    prospect_id: str,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    p = db.query(CRMProspect).filter(CRMProspect.id == prospect_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prospect not found")
    db.delete(p)
    db.commit()
