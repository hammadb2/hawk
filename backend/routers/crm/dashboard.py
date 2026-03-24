"""CRM Dashboard router — role-specific KPI stats."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, get_current_crm_user, get_visible_prospects_query
from backend.database import get_db
from backend.models.crm_client import CRMClient, CLIENT_STATUS_ACTIVE, CHURN_RISK_HIGH, CHURN_RISK_MEDIUM
from backend.models.crm_commission import CRMCommission
from backend.models.crm_prospect import CRMProspect, STAGE_CLOSED_WON
from backend.models.crm_task import CRMTask
from backend.models.crm_charlotte_email import CRMCharlotteEmail

router = APIRouter(prefix="/dashboard")


@router.get("/stats")
def get_dashboard_stats(
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    visible_q = get_visible_prospects_query(ctx, db)

    # Prospects
    total_prospects = visible_q.count()
    closes_this_month = visible_q.filter(
        CRMProspect.stage == STAGE_CLOSED_WON,
        CRMProspect.updated_at >= month_start,
    ).count()

    # Pipeline value (prospects in active stages × estimated MRR)
    open_prospects = visible_q.filter(
        CRMProspect.stage.notin_([STAGE_CLOSED_WON, "closed_lost"]),
    ).all()
    pipeline_value = sum(p.estimated_mrr or 99700 for p in open_prospects)  # cents

    # Tasks due today
    today_end = now.replace(hour=23, minute=59, second=59)
    tasks_due = db.query(CRMTask).filter(
        CRMTask.crm_user_id == ctx.crm_user_id,
        CRMTask.completed_at.is_(None),
        CRMTask.due_date <= today_end,
    ).count()

    # Commissions
    my_commission_month = db.query(func.sum(CRMCommission.amount)).filter(
        CRMCommission.crm_user_id == ctx.crm_user_id,
        CRMCommission.created_at >= month_start,
    ).scalar() or 0

    total_residual = db.query(func.sum(CRMCommission.amount)).filter(
        CRMCommission.crm_user_id == ctx.crm_user_id,
        CRMCommission.commission_type == "residual",
    ).scalar() or 0

    stats = {
        "total_prospects": total_prospects,
        "closes_this_month": closes_this_month,
        "pipeline_value_cents": pipeline_value,
        "tasks_due_today": tasks_due,
        "commission_this_month_cents": my_commission_month,
        "total_residual_cents": total_residual,
    }

    # CEO/HoS extra stats
    if ctx.has_full_visibility():
        active_clients = db.query(CRMClient).filter(
            CRMClient.status == CLIENT_STATUS_ACTIVE
        ).count()
        churn_risk_count = db.query(CRMClient).filter(
            CRMClient.status == CLIENT_STATUS_ACTIVE,
            CRMClient.churn_risk.in_([CHURN_RISK_HIGH, CHURN_RISK_MEDIUM]),
        ).count()
        total_mrr = db.query(func.sum(CRMClient.mrr)).filter(
            CRMClient.status == CLIENT_STATUS_ACTIVE
        ).scalar() or 0
        mrr_added_month = db.query(func.sum(CRMClient.mrr)).filter(
            CRMClient.status == CLIENT_STATUS_ACTIVE,
            CRMClient.closed_at >= month_start,
        ).scalar() or 0
        charlotte_today = db.query(CRMCharlotteEmail).filter(
            CRMCharlotteEmail.sent_at >= now.replace(hour=0, minute=0, second=0),
        ).count()

        stats.update({
            "active_clients": active_clients,
            "churn_risk_count": churn_risk_count,
            "total_mrr_cents": total_mrr,
            "mrr_added_this_month_cents": mrr_added_month,
            "charlotte_emails_today": charlotte_today,
        })

    return stats
