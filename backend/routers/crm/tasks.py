"""CRM Tasks router — follow-up tasks per rep."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, get_current_crm_user
from backend.database import get_db
from backend.models.crm_task import CRMTask
from backend.models.crm_user import CRMUser, CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD
from backend.schemas.crm_task import CRMTaskCreate, CRMTaskUpdate, CRMTaskOut

router = APIRouter(prefix="/tasks")


def _build_out(t: CRMTask) -> CRMTaskOut:
    return CRMTaskOut(
        id=t.id,
        crm_user_id=t.crm_user_id,
        prospect_id=t.prospect_id,
        title=t.title,
        description=t.description,
        due_date=t.due_date,
        completed_at=t.completed_at,
        priority=t.priority,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("/", response_model=List[CRMTaskOut])
def list_tasks(
    completed: Optional[bool] = Query(None),
    prospect_id: Optional[str] = Query(None),
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    q = db.query(CRMTask)

    # Filter by visibility
    if ctx.has_full_visibility():
        pass  # see all
    elif ctx.is_team_lead():
        rep_ids = [r.id for r in db.query(CRMUser).filter(CRMUser.team_lead_id == ctx.crm_user_id).all()]
        visible_ids = rep_ids + [ctx.crm_user_id]
        q = q.filter(CRMTask.crm_user_id.in_(visible_ids))
    else:
        q = q.filter(CRMTask.crm_user_id == ctx.crm_user_id)

    if completed is True:
        q = q.filter(CRMTask.completed_at.isnot(None))
    elif completed is False:
        q = q.filter(CRMTask.completed_at.is_(None))

    if prospect_id:
        q = q.filter(CRMTask.prospect_id == prospect_id)

    tasks = q.order_by(CRMTask.due_date.asc()).all()
    return [_build_out(t) for t in tasks]


@router.post("/", response_model=CRMTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    body: CRMTaskCreate,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    t = CRMTask(
        id=str(uuid4()),
        crm_user_id=ctx.crm_user_id,
        prospect_id=body.prospect_id,
        title=body.title,
        description=body.description,
        due_date=body.due_date,
        priority=body.priority,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _build_out(t)


@router.put("/{task_id}", response_model=CRMTaskOut)
def update_task(
    task_id: str,
    body: CRMTaskUpdate,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    t = db.query(CRMTask).filter(CRMTask.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    if t.crm_user_id != ctx.crm_user_id and not ctx.has_full_visibility():
        raise HTTPException(status_code=403, detail="Not your task")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(t, field, val)
    t.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(t)
    return _build_out(t)


@router.put("/{task_id}/complete", response_model=CRMTaskOut)
def complete_task(
    task_id: str,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    t = db.query(CRMTask).filter(CRMTask.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    if t.crm_user_id != ctx.crm_user_id and not ctx.has_full_visibility():
        raise HTTPException(status_code=403, detail="Not your task")
    t.completed_at = datetime.now(timezone.utc)
    t.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(t)
    return _build_out(t)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    t = db.query(CRMTask).filter(CRMTask.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    if t.crm_user_id != ctx.crm_user_id and not ctx.has_full_visibility():
        raise HTTPException(status_code=403, detail="Not your task")
    db.delete(t)
    db.commit()
