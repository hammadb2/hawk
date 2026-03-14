from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User, Scan, IgnoredFinding
from backend.schemas import FindingSchema, IgnoreFindingRequest

router = APIRouter(tags=["findings"])


@router.get("/api/findings/{scan_id}")
def get_findings(
    scan_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scan = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    ignored = {r.finding_id: r for r in db.query(IgnoredFinding).filter(IgnoredFinding.user_id == user.id, IgnoredFinding.scan_id == scan_id).all()}
    findings = json.loads(scan.findings_json or "[]")
    out = []
    for f in findings:
        fid = f.get("id")
        ign = ignored.get(fid) if fid else None
        out.append({
            **f,
            "ignored": ign is not None,
            "ignore_reason": ign.reason if ign else None,
        })
    return {"findings": out, "scan_id": scan_id, "score": scan.score, "grade": scan.grade}


@router.post("/api/findings/{finding_id}/ignore")
def ignore_finding(
    finding_id: str,
    req: IgnoreFindingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # We need scan_id; accept in body or query. Spec says POST /api/findings/:id/ignore { reason }
    # So we need scan_id in body for context
    scan_id = req.scan_id
    if not scan_id:
        # Check if finding exists in any of user's scans
        scans = db.query(Scan).filter(Scan.user_id == user.id).all()
        for s in scans:
            if not s.findings_json:
                continue
            for f in json.loads(s.findings_json):
                if f.get("id") == finding_id:
                    scan_id = s.id
                    break
            if scan_id:
                break
    if not scan_id:
        raise HTTPException(status_code=400, detail="scan_id required or finding not found")
    existing = db.query(IgnoredFinding).filter(
        IgnoredFinding.user_id == user.id,
        IgnoredFinding.finding_id == finding_id,
        IgnoredFinding.scan_id == scan_id,
    ).first()
    if existing:
        return {"message": "Already ignored"}
    ign = IgnoredFinding(
        id=str(uuid4()),
        user_id=user.id,
        finding_id=finding_id,
        scan_id=scan_id,
        reason=req.reason,
    )
    db.add(ign)
    db.commit()
    return {"message": "Finding ignored"}


@router.post("/api/findings/{finding_id}/fix")
def fix_finding(
    finding_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trigger rescan of the specific check. Returns new scan_id."""
    # Find which scan contains this finding and which check category to rescan
    from sqlalchemy import desc
    scans = db.query(Scan).filter(Scan.user_id == user.id).order_by(desc(Scan.started_at)).limit(50).all()
    domain_str = None
    for s in scans:
        if not s.findings_json:
            continue
        for f in json.loads(s.findings_json):
            if f.get("id") == finding_id:
                domain_str = s.scanned_domain or (s.domain.domain if s.domain else None)
                break
        if domain_str:
            break
    if not domain_str:
        raise HTTPException(status_code=404, detail="Finding not found")
    from backend.services.scanner import run_scan
    new_id = str(uuid4())
    result = run_scan(domain_str, scan_id=new_id)
    from datetime import datetime, timezone
    new_scan = Scan(
        id=new_id,
        user_id=user.id,
        scanned_domain=domain_str,
        triggered_by="user",
        status=result.get("status", "completed"),
        score=result.get("score"),
        grade=result.get("grade"),
        findings_json=json.dumps(result.get("findings", [])),
        started_at=datetime.fromisoformat(result["started_at"].replace("Z", "+00:00")) if result.get("started_at") else datetime.now(timezone.utc),
        completed_at=datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00")) if result.get("completed_at") else datetime.now(timezone.utc),
    )
    db.add(new_scan)
    db.commit()
    return {"message": "Rescan triggered", "scan_id": new_id}