"""CRM Charlotte router — automated email outreach management."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.orm import Session

from backend.auth_crm import CRMContext, require_role
from backend.database import get_db
from backend.models.crm_charlotte_email import (
    CRMCharlotteEmail,
    EMAIL_STATUS_SENT,
    EMAIL_STATUS_OPENED,
    EMAIL_STATUS_REPLIED,
    EMAIL_STATUS_BOUNCED,
    EMAIL_STATUS_DELIVERED,
)
from backend.models.crm_prospect import CRMProspect, STAGE_REPLIED, SOURCE_CHARLOTTE
from backend.models.crm_user import CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES
from backend.schemas.crm_charlotte import (
    CRMCampaignCreate,
    CRMCharlotteEmailOut,
    CRMCharlotteStats,
    CRMCharlotteWebhookEvent,
)
from backend.config import CHARLOTTE_API_KEY

router = APIRouter(prefix="/charlotte")


def _build_out(e: CRMCharlotteEmail) -> CRMCharlotteEmailOut:
    return CRMCharlotteEmailOut(
        id=e.id,
        prospect_id=e.prospect_id,
        to_email=e.to_email,
        subject=e.subject,
        status=e.status,
        sent_at=e.sent_at,
        opened_at=e.opened_at,
        replied_at=e.replied_at,
        created_at=e.created_at,
    )


@router.get("/emails", response_model=List[CRMCharlotteEmailOut])
def list_charlotte_emails(
    email_status: Optional[str] = Query(None, alias="status"),
    prospect_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    q = db.query(CRMCharlotteEmail)
    if email_status:
        q = q.filter(CRMCharlotteEmail.status == email_status)
    if prospect_id:
        q = q.filter(CRMCharlotteEmail.prospect_id == prospect_id)
    items = q.order_by(CRMCharlotteEmail.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return [_build_out(e) for e in items]


@router.get("/stats", response_model=CRMCharlotteStats)
def get_charlotte_stats(
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    sent_today = db.query(CRMCharlotteEmail).filter(
        CRMCharlotteEmail.sent_at >= today_start
    ).count()
    total_sent = db.query(CRMCharlotteEmail).count()
    total_opened = db.query(CRMCharlotteEmail).filter(
        CRMCharlotteEmail.status.in_([EMAIL_STATUS_OPENED, EMAIL_STATUS_REPLIED])
    ).count()
    total_replied = db.query(CRMCharlotteEmail).filter(
        CRMCharlotteEmail.status == EMAIL_STATUS_REPLIED
    ).count()
    total_bounced = db.query(CRMCharlotteEmail).filter(
        CRMCharlotteEmail.status == EMAIL_STATUS_BOUNCED
    ).count()

    open_rate = round(total_opened / total_sent, 4) if total_sent > 0 else 0.0
    reply_rate = round(total_replied / total_sent, 4) if total_sent > 0 else 0.0

    return CRMCharlotteStats(
        sent_today=sent_today,
        total_sent=total_sent,
        total_opened=total_opened,
        total_replied=total_replied,
        total_bounced=total_bounced,
        open_rate=open_rate,
        reply_rate=reply_rate,
    )


@router.post("/campaign", status_code=status.HTTP_201_CREATED)
def create_campaign(
    body: CRMCampaignCreate,
    ctx: CRMContext = Depends(require_role(CRM_ROLE_CEO, CRM_ROLE_HEAD_OF_SALES)),
    db: Session = Depends(get_db),
):
    """Queue outreach emails for a list of targets. Creates prospect records if needed."""
    if not body.targets:
        raise HTTPException(status_code=400, detail="No targets provided")

    now = datetime.now(timezone.utc)
    created_emails = 0

    for target in body.targets:
        email = (target.get("contact_email") or "").strip()
        company_name = (target.get("company_name") or "").strip()
        domain = (target.get("domain") or "").strip() or None

        if not email or not company_name:
            continue

        # Find or create prospect
        prospect = None
        if domain:
            prospect = db.query(CRMProspect).filter(CRMProspect.domain == domain).first()
        if not prospect:
            prospect = CRMProspect(
                id=str(uuid4()),
                company_name=company_name,
                domain=domain,
                contact_name=target.get("contact_name"),
                contact_email=email,
                source=SOURCE_CHARLOTTE,
            )
            db.add(prospect)
            db.flush()

        # Personalise subject and body (simple template substitution)
        subject = body.subject_template.replace("{{company}}", company_name)
        body_text = body.body_template.replace("{{company}}", company_name).replace(
            "{{contact_name}}", target.get("contact_name") or "there"
        )

        charlotte_email = CRMCharlotteEmail(
            id=str(uuid4()),
            prospect_id=prospect.id,
            to_email=email,
            subject=subject,
            body=body_text,
            status=EMAIL_STATUS_SENT,
            sent_at=now,
        )
        db.add(charlotte_email)
        created_emails += 1

    db.commit()
    return {"queued": created_emails}


@router.post("/webhook")
def charlotte_webhook(
    body: CRMCharlotteWebhookEvent,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Receive email events from Charlotte (opened, replied, bounced). Auth via X-Api-Key."""
    if not x_api_key or x_api_key != CHARLOTTE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    email_record = db.query(CRMCharlotteEmail).filter(CRMCharlotteEmail.id == body.email_id).first()
    if not email_record:
        raise HTTPException(status_code=404, detail="Email record not found")

    now = body.timestamp or datetime.now(timezone.utc)
    event = body.event.lower()

    if event == "opened":
        email_record.status = EMAIL_STATUS_OPENED
        email_record.opened_at = now
    elif event == "replied":
        email_record.status = EMAIL_STATUS_REPLIED
        email_record.replied_at = now
        # Move prospect to Replied stage
        prospect = email_record.prospect
        if prospect and prospect.stage not in ("replied", "call_booked", "proposal_sent", "closed_won", "closed_lost"):
            prospect.stage = STAGE_REPLIED
            prospect.updated_at = now
    elif event == "bounced":
        email_record.status = EMAIL_STATUS_BOUNCED
    elif event == "delivered":
        email_record.status = EMAIL_STATUS_DELIVERED

    email_record.updated_at = now
    db.commit()
    return {"ok": True}
