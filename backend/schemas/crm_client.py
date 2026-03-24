"""Pydantic schemas for CRM clients."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CRMClientUpdate(BaseModel):
    mrr: Optional[int] = None  # cents
    churn_risk: Optional[str] = None
    churn_risk_reason: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None


class CRMClientChurn(BaseModel):
    reason: Optional[str] = None


class CRMClientOut(BaseModel):
    id: str
    prospect_id: Optional[str]
    company_name: str
    domain: Optional[str]
    contact_name: Optional[str]
    contact_email: Optional[str]
    mrr: int  # cents
    closed_by_rep_id: Optional[str]
    closed_by_rep_name: Optional[str] = None
    closed_at: Optional[datetime]
    churn_risk: str
    churn_risk_reason: Optional[str]
    status: str
    churned_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
