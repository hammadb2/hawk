from __future__ import annotations

from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    scan_id: str
    sections: list[str] = Field(default_factory=lambda: ["executive", "findings", "compliance"])


class ReportListItem(BaseModel):
    id: str
    scan_id: str
    domain: str
    pdf_path: str | None
    created_at: str

    class Config:
        from_attributes = True


class ReportResponse(BaseModel):
    id: str
    user_id: str
    scan_id: str
    domain: str
    pdf_path: str | None
    created_at: str

    class Config:
        from_attributes = True
