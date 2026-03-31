from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User, Notification

router = APIRouter(tags=["notifications"])


def _notif_response(n: Notification) -> dict:
    return {
        "id": n.id,
        "user_id": n.user_id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/api/notifications")
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notifs = db.query(Notification).filter(Notification.user_id == user.id).order_by(desc(Notification.created_at)).limit(50).all()
    return {"notifications": [_notif_response(n) for n in notifs]}


@router.post("/api/notifications/read-all")
def read_all(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read == False).update({"read": True})
    db.commit()
    return {"message": "All notifications marked as read"}
