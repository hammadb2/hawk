from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User, Domain
from backend.schemas import DomainCreate, DomainUpdate, DomainResponse
from backend.config import PLAN_DOMAINS

router = APIRouter(tags=["domains"])


def _domain_response(d: Domain) -> dict:
    return {
        "id": d.id,
        "user_id": d.user_id,
        "domain": d.domain,
        "label": d.label,
        "scan_frequency": d.scan_frequency,
        "notify_email": d.notify_email,
        "notify_slack": d.notify_slack,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


@router.get("/api/domains")
def list_domains(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    domains = db.query(Domain).filter(Domain.user_id == user.id).all()
    return {"domains": [_domain_response(d) for d in domains]}


@router.post("/api/domains")
def create_domain(
    req: DomainCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = user.plan
    limit = PLAN_DOMAINS.get(plan, 0)
    if limit >= 0:
        count = db.query(Domain).filter(Domain.user_id == user.id).count()
        if count >= limit:
            raise HTTPException(status_code=403, detail=f"Plan {plan} allows max {limit} domain(s)")
    domain_clean = req.domain.lower().strip().replace("http://", "").replace("https://", "").split("/")[0]
    if domain_clean.startswith("www."):
        domain_clean = domain_clean[4:]
    existing = db.query(Domain).filter(Domain.user_id == user.id, Domain.domain == domain_clean).first()
    if existing:
        raise HTTPException(status_code=400, detail="Domain already added")
    d = Domain(
        id=str(uuid4()),
        user_id=user.id,
        domain=domain_clean,
        label=req.label,
        scan_frequency=req.scan_frequency or "on_demand",
        notify_email=req.notify_email,
        notify_slack=req.notify_slack,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _domain_response(d)


@router.put("/api/domains/{domain_id}")
def update_domain(
    domain_id: str,
    req: DomainUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    d = db.query(Domain).filter(Domain.id == domain_id, Domain.user_id == user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Domain not found")
    if req.label is not None:
        d.label = req.label
    if req.scan_frequency is not None:
        d.scan_frequency = req.scan_frequency
    if req.notify_email is not None:
        d.notify_email = req.notify_email
    if req.notify_slack is not None:
        d.notify_slack = req.notify_slack
    db.commit()
    db.refresh(d)
    return _domain_response(d)


@router.delete("/api/domains/{domain_id}")
def delete_domain(
    domain_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    d = db.query(Domain).filter(Domain.id == domain_id, Domain.user_id == user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Domain not found")
    db.delete(d)
    db.commit()
    return {"message": "Domain deleted"}
