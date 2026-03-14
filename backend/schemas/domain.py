from __future__ import annotations

from pydantic import BaseModel, Field


class DomainCreate(BaseModel):
    domain: str = Field(..., min_length=1)
    label: str | None = None
    scan_frequency: str | None = "on_demand"
    notify_email: str | None = None
    notify_slack: str | None = None


class DomainUpdate(BaseModel):
    label: str | None = None
    scan_frequency: str | None = None
    notify_email: str | None = None
    notify_slack: str | None = None


class DomainResponse(BaseModel):
    id: str
    user_id: str
    domain: str
    label: str | None
    scan_frequency: str | None
    notify_email: str | None
    notify_slack: str | None
    created_at: str

    class Config:
        from_attributes = True
