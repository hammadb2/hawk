from __future__ import annotations

from pydantic import BaseModel, Field


class FindingSchema(BaseModel):
    id: str
    severity: str
    category: str
    title: str
    description: str
    technical_detail: str
    affected_asset: str
    remediation: str
    compliance: list[str] = Field(default_factory=list)
    ignored: bool = False
    ignore_reason: str | None = None


class IgnoreFindingRequest(BaseModel):
    reason: str | None = None
    scan_id: str | None = None  # optional; if not set, we look up by finding_id in user's scans
