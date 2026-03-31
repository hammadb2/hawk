"""Scan DTOs — compatible with Specter `specter_scanner.py` response shape."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Finding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    severity: str  # critical | high | medium | low | warning | info | ok
    category: str
    title: str
    description: str
    technical_detail: str = ""
    affected_asset: str = ""
    remediation: str = ""
    compliance: list[str] = Field(default_factory=list)
    layer: str | None = None
    raw_ref: str | None = None
    interpretation: str | None = None
    fix_guide: str | None = None


class ScanResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scan_id: str | None = None
    domain: str
    status: str = "completed"
    score: int = Field(..., ge=0, le=100)
    grade: str
    findings: list[Finding] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    scan_version: str = "2.0"
    industry: str | None = None
    industry_risk_multiplier: float = 1.0
    raw_layers: dict = Field(default_factory=dict)
    interpreted_findings: list[dict] = Field(default_factory=list)
    breach_cost_estimate: dict = Field(default_factory=dict)


class ScanRequest(BaseModel):
    domain: str = Field(..., min_length=1)
    scan_id: str | None = None
    industry: str | None = Field(None, description="Prospect industry for risk multiplier")
