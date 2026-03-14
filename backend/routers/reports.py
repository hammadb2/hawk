from __future__ import annotations

import os
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User, Scan, Report
from backend.schemas import ReportGenerateRequest
from backend.config import PLAN_PDF_PER_MONTH
from backend.services.report_pdf import render_report_pdf

router = APIRouter(tags=["reports"])

REPORTS_DIR = Path(os.environ.get("HAWK_REPORTS_DIR", "./reports"))


@router.get("/api/reports")
def list_reports(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reports = db.query(Report).filter(Report.user_id == user.id).order_by(desc(Report.created_at)).limit(50).all()
    return {
        "reports": [
            {"id": r.id, "scan_id": r.scan_id, "domain": r.domain, "pdf_path": r.pdf_path, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in reports
        ]
    }


@router.post("/api/reports/generate")
def generate_report(
    req: ReportGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = PLAN_PDF_PER_MONTH.get(user.plan, 0)
    if limit >= 0:
        from datetime import timedelta
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = db.query(Report).filter(Report.user_id == user.id, Report.created_at >= month_start).count()
        if count >= limit:
            raise HTTPException(status_code=403, detail=f"Plan allows {limit} PDF(s) per month")
    scan = db.query(Scan).filter(Scan.id == req.scan_id, Scan.user_id == user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    domain_str = scan.scanned_domain or (scan.domain.domain if scan.domain else "unknown")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_id = str(uuid4())
    pdf_filename = f"{report_id}.pdf"
    pdf_path = REPORTS_DIR / pdf_filename
    sections = req.sections or ["executive", "findings", "compliance"]
    if not render_report_pdf(scan, sections, pdf_path):
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n")
    rel_path = str(pdf_path)
    r = Report(
        id=report_id,
        user_id=user.id,
        scan_id=scan.id,
        domain=domain_str,
        pdf_path=rel_path,
    )
    db.add(r)
    db.commit()
    return {"id": r.id, "scan_id": r.scan_id, "domain": r.domain, "pdf_path": r.pdf_path, "created_at": r.created_at.isoformat() if r.created_at else None}


@router.get("/api/reports/{report_id}/pdf")
def get_report_pdf(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = db.query(Report).filter(Report.id == report_id, Report.user_id == user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    path = Path(r.pdf_path) if r.pdf_path else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(path, media_type="application/pdf", filename=f"hawk-report-{r.domain}.pdf")
