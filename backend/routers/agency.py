from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User, AgencyClient, Scan, Report
from schemas import AgencyClientCreate
from services.report_pdf import render_report_pdf

router = APIRouter(prefix="/api/agency", tags=["agency"])


def _client_response(c: AgencyClient) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "name": c.name,
        "email": c.email,
        "company": c.company,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/clients")
def list_clients(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.plan != "agency":
        raise HTTPException(status_code=403, detail="Agency plan required")
    clients = db.query(AgencyClient).filter(AgencyClient.user_id == user.id).all()
    return {"clients": [_client_response(c) for c in clients]}


@router.post("/clients")
def create_client(
    req: AgencyClientCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.plan != "agency":
        raise HTTPException(status_code=403, detail="Agency plan required")
    c = AgencyClient(
        id=str(uuid4()),
        user_id=user.id,
        name=req.name,
        email=req.email,
        company=req.company,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _client_response(c)


@router.get("/clients/{client_id}")
def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.plan != "agency":
        raise HTTPException(status_code=403, detail="Agency plan required")
    c = db.query(AgencyClient).filter(AgencyClient.id == client_id, AgencyClient.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return _client_response(c)


@router.delete("/clients/{client_id}")
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.plan != "agency":
        raise HTTPException(status_code=403, detail="Agency plan required")
    c = db.query(AgencyClient).filter(AgencyClient.id == client_id, AgencyClient.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(c)
    db.commit()
    return {"message": "Client deleted"}


@router.post("/clients/{client_id}/report")
def create_client_report(
    client_id: str,
    body: dict | None = Body(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.plan != "agency":
        raise HTTPException(status_code=403, detail="Agency plan required")
    c = db.query(AgencyClient).filter(AgencyClient.id == client_id, AgencyClient.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    scan_id = (body or {}).get("scan_id") if isinstance(body, dict) else None
    if scan_id:
        scan = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
    else:
        scan = db.query(Scan).filter(Scan.user_id == user.id).order_by(desc(Scan.completed_at)).first()
        if not scan:
            raise HTTPException(status_code=400, detail="No scans yet. Run a scan first.")
    domain_str = scan.scanned_domain or (scan.domain.domain if getattr(scan, "domain", None) and scan.domain else "unknown")
    reports_dir = Path(os.environ.get("HAWK_REPORTS_DIR", "./reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_id = str(uuid4())
    pdf_path = reports_dir / f"{report_id}.pdf"
    sections = ["executive", "findings", "compliance"]
    if not render_report_pdf(scan, sections, pdf_path, client_name=c.name, client_company=c.company or None):
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n")
    r = Report(id=report_id, user_id=user.id, scan_id=scan.id, domain=domain_str, pdf_path=str(pdf_path))
    db.add(r)
    db.commit()
    return {"report_id": report_id, "message": "Report generated", "download_path": f"/api/reports/{report_id}/pdf"}
