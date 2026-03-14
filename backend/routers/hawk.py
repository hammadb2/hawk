from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime, timezone

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User, Scan, HawkMessage
from backend.schemas import HawkChatRequest, HawkChatResponse
from backend.services.hawk_chat import build_system_prompt, chat
from backend.config import PLAN_ASK_HAWK_LIMIT

router = APIRouter(prefix="/api/hawk", tags=["ask-hawk"])


@router.post("/chat", response_model=HawkChatResponse)
def hawk_chat(
    req: HawkChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = PLAN_ASK_HAWK_LIMIT.get(user.plan, 0)
    if limit >= 0:
        row = db.query(HawkMessage).filter(HawkMessage.user_id == user.id).first()
        if not row:
            row = HawkMessage(id=str(uuid4()), user_id=user.id, message_count=0)
            db.add(row)
            db.commit()
            db.refresh(row)
        if row.message_count >= limit:
            raise HTTPException(
                status_code=403,
                detail="Ask HAWK message limit reached for your plan. Upgrade for unlimited messages.",
            )
        row.message_count += 1
        row.updated_at = datetime.now(timezone.utc)
        db.commit()

    findings_json = None
    score = None
    grade = None
    domain = "the user's domain"
    if req.scan_id:
        scan = db.query(Scan).filter(Scan.id == req.scan_id, Scan.user_id == user.id).first()
        if scan:
            findings_json = scan.findings_json
            score = scan.score
            grade = scan.grade
            domain = scan.scanned_domain or (scan.domain.domain if scan.domain else "the scanned domain")

    system_prompt = build_system_prompt(
        findings_json=findings_json,
        score=score,
        grade=grade,
        domain=domain,
        industry=user.industry,
        province=user.province,
        plan=user.plan,
    )
    reply, trigger_rescan = chat(
        message=req.message,
        system_prompt=system_prompt,
        conversation_history=req.conversation_history,
    )
    return HawkChatResponse(reply=reply, trigger_rescan=trigger_rescan)
