"""Pydantic schemas for CRM Charlotte email outreach."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class CRMCampaignCreate(BaseModel):
    targets: List[dict]  # [{company_name, domain, contact_email, contact_name}]
    subject_template: str
    body_template: str


class CRMCharlotteEmailOut(BaseModel):
    id: str
    prospect_id: str
    to_email: str
    subject: Optional[str]
    status: str
    sent_at: Optional[datetime]
    opened_at: Optional[datetime]
    replied_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class CRMCharlotteStats(BaseModel):
    sent_today: int
    total_sent: int
    total_opened: int
    total_replied: int
    total_bounced: int
    open_rate: float
    reply_rate: float


class CRMCharlotteWebhookEvent(BaseModel):
    email_id: str
    event: str  # opened, replied, bounced, delivered
    timestamp: Optional[datetime] = None
