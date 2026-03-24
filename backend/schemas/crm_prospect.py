"""Pydantic schemas for CRM prospects."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class CRMProspectCreate(BaseModel):
    company_name: str
    domain: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    source: str = "manual"
    notes: Optional[str] = None
    estimated_mrr: Optional[int] = None  # cents
    assigned_rep_id: Optional[str] = None


class CRMProspectUpdate(BaseModel):
    company_name: Optional[str] = None
    domain: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None
    estimated_mrr: Optional[int] = None
    lost_reason: Optional[str] = None


class CRMProspectStageUpdate(BaseModel):
    stage: str
    lost_reason: Optional[str] = None
    note: Optional[str] = None  # optional activity note


class CRMProspectAssign(BaseModel):
    assigned_rep_id: Optional[str] = None  # null to unassign


class CRMProspectOut(BaseModel):
    id: str
    company_name: str
    domain: Optional[str]
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    industry: Optional[str]
    city: Optional[str]
    stage: str
    hawk_score: Optional[int]
    assigned_rep_id: Optional[str]
    assigned_rep_name: Optional[str] = None
    source: str
    notes: Optional[str]
    estimated_mrr: Optional[int]
    lost_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
