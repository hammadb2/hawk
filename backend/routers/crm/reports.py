"""CRM Reports router — revenue, pipeline, and commission reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, require_role
from backend.database import get_db
from backend.models.crm_client import CRMClient, CLIENT_STATUS_ACTIVE
from backend.models.crm_commission import CRMCommission
from backend.models.crm_prospect import CRMProspect, PIPELINE_STAGES, STAGE_CLOSED_WON
from backend.models.crm_user import CRMUser, CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD

router = APIRouter(prefix="/reports")


@router.get("/revenue")
def revenue_report(
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    """MRR breakdown: total, by rep, monthly trend."""
    total_mrr = db.query(func.sum(CRMClient.mrr)).filter(
        CRMClient.status == CLIENT_STATUS_ACTIVE
    ).scalar() or 0

    # MRR by rep
    by_rep_raw = db.query(
        CRMClient.closed_by_rep_id,
        func.sum(CRMClient.mrr).label("mrr"),
        func.count(CRMClient.id).label("clients"),
    ).filter(
        CRMClient.status == CLIENT_STATUS_ACTIVE
    ).group_by(CRMClient.closed_by_rep_id).all()

    by_rep = []
    for row in by_rep_raw:
        rep = db.query(CRMUser).filter(CRMUser.id == row.closed_by_rep_id).first()
        rep_name = ""
        if rep and rep.user:
            rep_name = f"{rep.user.first_name or ''} {rep.user.last_name or ''}".strip() or rep.user.email
        by_rep.append({
            "crm_user_id": row.closed_by_rep_id,
            "rep_name": rep_name,
            "mrr_cents": row.mrr,
            "active_clients": row.clients,
        })

    return {
        "total_mrr_cents": total_mrr,
        "active_clients": db.query(CRMClient).filter(CRMClient.status == CLIENT_STATUS_ACTIVE).count(),
        "by_rep": by_rep,
    }


@router.get("/pipeline")
def pipeline_report(
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD)),
    db: Session = Depends(get_db),
):
    """Prospect counts per stage and conversion rates."""
    stage_counts = []
    for stage in PIPELINE_STAGES:
        q = db.query(CRMProspect).filter(CRMProspect.stage == stage)
        if ctx.is_team_lead():
            rep_ids = [r.id for r in db.query(CRMUser).filter(CRMUser.team_lead_id == ctx.crm_user_id).all()]
            q = q.filter(CRMProspect.assigned_rep_id.in_(rep_ids + [ctx.crm_user_id]))
        count = q.count()
        stage_counts.append({"stage": stage, "count": count})

    total = sum(s["count"] for s in stage_counts)
    return {"stages": stage_counts, "total": total}


@router.get("/commissions")
def commission_report(
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    """Commission summary by rep — total earned, paid, unpaid."""
    reps = db.query(CRMUser).filter(CRMUser.is_active == True).all()  # noqa: E712
    result = []
    for rep in reps:
        total = db.query(func.sum(CRMCommission.amount)).filter(
            CRMCommission.crm_user_id == rep.id
        ).scalar() or 0
        paid = db.query(func.sum(CRMCommission.amount)).filter(
            CRMCommission.crm_user_id == rep.id,
            CRMCommission.paid == True,  # noqa: E712
        ).scalar() or 0
        user = rep.user
        result.append({
            "crm_user_id": rep.id,
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "",
            "total_earned_cents": total,
            "paid_cents": paid,
            "unpaid_cents": total - paid,
        })
    return {"reps": result}
