"""Pydantic schemas for CRM commissions."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel


class CRMCommissionCreate(BaseModel):
    crm_user_id: str
    client_id: str
    commission_type: str  # closing or residual
    amount: int           # cents
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class CRMCommissionOut(BaseModel):
    id: str
    crm_user_id: str
    client_id: str
    commission_type: str
    amount: int  # cents
    period_start: Optional[date]
    period_end: Optional[date]
    paid: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
