"""Pydantic schemas for CRM team/user management."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class CRMUserBase(BaseModel):
    crm_role: str
    monthly_target: int = 0
    team_lead_id: Optional[str] = None


class CRMUserCreate(CRMUserBase):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: str


class CRMUserUpdate(BaseModel):
    crm_role: Optional[str] = None
    monthly_target: Optional[int] = None
    team_lead_id: Optional[str] = None
    is_active: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class CRMUserOut(BaseModel):
    id: str
    user_id: str
    crm_role: str
    monthly_target: int
    team_lead_id: Optional[str]
    is_active: bool
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CRMUserStats(CRMUserOut):
    closes_this_month: int = 0
    mrr_closed_this_month: int = 0  # cents
    total_prospects: int = 0
    commission_this_month: int = 0  # cents
