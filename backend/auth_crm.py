"""CRM-specific auth dependencies — role checking and visibility filtering."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session, Query

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User
from backend.models.crm_user import CRMUser, CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES, CRM_ROLE_TEAM_LEAD
from backend.models.crm_prospect import CRMProspect


@dataclass
class CRMContext:
    """Combined context for a CRM-authenticated request."""
    user: User
    crm_user: CRMUser

    @property
    def role(self) -> str:
        return self.crm_user.crm_role

    @property
    def crm_user_id(self) -> str:
        return self.crm_user.id

    def is_ceo(self) -> bool:
        return self.role == CRM_ROLE_CEO

    def is_head_of_sales(self) -> bool:
        return self.role == CRM_ROLE_HEAD_OF_SALES

    def is_team_lead(self) -> bool:
        return self.role == CRM_ROLE_TEAM_LEAD

    def has_full_visibility(self) -> bool:
        return self.role in (CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)


def get_current_crm_user(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CRMContext:
    """Load CRM profile for the authenticated user. Raises 403 if not a CRM user."""
    crm_user = db.query(CRMUser).filter(
        CRMUser.user_id == user.id,
        CRMUser.is_active == True,  # noqa: E712
    ).first()
    if not crm_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a CRM user",
        )
    return CRMContext(user=user, crm_user=crm_user)


def require_role(*allowed_roles: str) -> Callable:
    """Factory returning a dependency that enforces role membership."""
    def dependency(ctx: CRMContext = Depends(get_current_crm_user)) -> CRMContext:
        if ctx.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{ctx.role}' is not allowed for this action",
            )
        return ctx
    return dependency


def get_visible_prospects_query(ctx: CRMContext, db: Session) -> Query:
    """Return a filtered query for prospects visible to the current CRM user."""
    base = db.query(CRMProspect)

    if ctx.has_full_visibility():
        return base  # CEO and HoS see everything

    if ctx.is_team_lead():
        # Team lead sees their own prospects + prospects of their reps
        rep_ids = [
            r.id for r in db.query(CRMUser).filter(CRMUser.team_lead_id == ctx.crm_user_id).all()
        ]
        visible_ids = rep_ids + [ctx.crm_user_id]
        return base.filter(CRMProspect.assigned_rep_id.in_(visible_ids))

    # Sales rep sees only own prospects
    return base.filter(CRMProspect.assigned_rep_id == ctx.crm_user_id)
