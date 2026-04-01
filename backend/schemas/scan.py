from __future__ import annotations

from pydantic import BaseModel, Field


class ScanStartRequest(BaseModel):
    """Public scan body. full_result=True returns full scanner JSON for CRM/debug; default is slim."""

    domain: str = Field(..., min_length=1)
    full_result: bool = False


class ScanEnqueueRequest(BaseModel):
    domain: str = Field(..., min_length=1)
    industry: str | None = None


class ScanListItem(BaseModel):
    id: str
    domain_id: str | None
    user_id: str
    status: str
    score: int | None
    grade: str | None
    started_at: str | None
    completed_at: str | None

    class Config:
        from_attributes = True


class ScanResponse(BaseModel):
    id: str
    domain_id: str | None
    user_id: str
    triggered_by: str | None
    status: str
    score: int | None
    grade: str | None
    findings_json: str | None
    started_at: str | None
    completed_at: str | None

    class Config:
        from_attributes = True
