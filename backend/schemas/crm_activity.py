"""Pydantic schemas for CRM activities."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CRMActivityCreate(BaseModel):
    prospect_id: str
    activity_type: str
    description: Optional[str] = None


class CRMActivityOut(BaseModel):
    id: str
    prospect_id: str
    crm_user_id: Optional[str]
    crm_user_name: Optional[str] = None
    activity_type: str
    description: Optional[str]
    old_stage: Optional[str]
    new_stage: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
