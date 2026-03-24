"""CRM Scoreboard router — rep leaderboard ranked by closes."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, get_current_crm_user
from backend.database import get_db
from backend.models.crm_commission import CRMCommission
from backend.models.crm_prospect import CRMProspect, STAGE_CLOSED_WON
from backend.models.crm_user import CRMUser

router = APIRouter(prefix="/scoreboard")


@router.get("/")
def get_scoreboard(
    period: str = Query("month", pattern="^(week|month|quarter|all)$"),
    ctx: CRMContext = Depends(get_current_crm_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    if period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        quarter_month = ((now.month - 1) // 3) * 3 + 1
        since = now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        since = None  # all time

    reps = db.query(CRMUser).filter(CRMUser.is_active == True).all()  # noqa: E712

    rows = []
    for rep in reps:
        closes_q = db.query(CRMProspect).filter(
            CRMProspect.assigned_rep_id == rep.id,
            CRMProspect.stage == STAGE_CLOSED_WON,
        )
        commission_q = db.query(func.sum(CRMCommission.amount)).filter(
            CRMCommission.crm_user_id == rep.id,
        )
        if since:
            closes_q = closes_q.filter(CRMProspect.updated_at >= since)
            commission_q = commission_q.filter(CRMCommission.created_at >= since)

        closes = closes_q.count()
        commission = commission_q.scalar() or 0
        user = rep.user

        rows.append({
            "crm_user_id": rep.id,
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else rep.id,
            "email": user.email if user else "",
            "role": rep.crm_role,
            "monthly_target": rep.monthly_target,
            "closes": closes,
            "commission_cents": commission,
            "on_pace": closes >= rep.monthly_target if rep.monthly_target > 0 else None,
        })

    rows.sort(key=lambda r: r["closes"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    # Find current user's rank
    my_entry = next((r for r in rows if r["crm_user_id"] == ctx.crm_user_id), None)

    return {
        "period": period,
        "leaderboard": rows,
        "my_rank": my_entry["rank"] if my_entry else None,
        "total_reps": len(rows),
    }
