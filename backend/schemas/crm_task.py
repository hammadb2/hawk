"""Pydantic schemas for CRM tasks."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CRMTaskCreate(BaseModel):
    prospect_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str = "medium"


class CRMTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = None


class CRMTaskOut(BaseModel):
    id: str
    crm_user_id: str
    prospect_id: Optional[str]
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
    priority: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
