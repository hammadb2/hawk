"""CRM Settings router — commission rates and configuration (CEO only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, require_role
from backend.database import get_db
from backend.models.crm_user import CRM_ROLE_CEO

router = APIRouter(prefix="/settings")

# In-memory defaults (replace with DB-backed config table if needed)
_CRM_SETTINGS: dict = {
    "closing_commission_rate": 0.10,       # 10% of first month MRR
    "residual_commission_rate": 0.05,      # 5% of MRR per month
    "default_prospect_mrr_cents": 99700,  # $997
    "pipeline_stages": [
        "new", "scanned", "loom_sent", "replied",
        "call_booked", "proposal_sent", "closed_won", "closed_lost",
    ],
}


class CRMSettingsUpdate(BaseModel):
    closing_commission_rate: float | None = None
    residual_commission_rate: float | None = None
    default_prospect_mrr_cents: int | None = None


@router.get("/")
def get_settings(ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO))):
    return _CRM_SETTINGS


@router.put("/")
def update_settings(
    body: CRMSettingsUpdate,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO)),
):
    updated = dict(_CRM_SETTINGS)
    if body.closing_commission_rate is not None:
        updated["closing_commission_rate"] = body.closing_commission_rate
    if body.residual_commission_rate is not None:
        updated["residual_commission_rate"] = body.residual_commission_rate
    if body.default_prospect_mrr_cents is not None:
        updated["default_prospect_mrr_cents"] = body.default_prospect_mrr_cents
    _CRM_SETTINGS.update(updated)
    return _CRM_SETTINGS
