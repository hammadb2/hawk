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
    breach_source: str | None = Field(
        default=None,
        description="Sub-source when layer is breach_monitoring (hudson_rock, ransomwatch, …)",
    )
    raw_ref: str | None = None
    interpretation: str | None = None
    fix_guide: str | None = None
    screenshot_data_url: str | None = Field(
        default=None,
        description="JPEG data URL for exposure_screenshot layer (portal/CRM display)",
    )


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
    attack_paths: list[dict] = Field(default_factory=list)


class ScanRequest(BaseModel):
    domain: str = Field(..., min_length=1)
    scan_id: str | None = None
    industry: str | None = Field(None, description="Prospect industry for risk multiplier")
    company_name: str | None = Field(None, description="Display name for narrative features (attack paths)")
    scan_depth: str = Field(
        default="full",
        description="full = all pipeline layers; fast = Charlotte tier (email, TLS, breach, subdomains)",
    )
