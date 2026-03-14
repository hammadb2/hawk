from __future__ import annotations

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str | None
    title: str
    body: str | None
    read: bool
    created_at: str

    class Config:
        from_attributes = True
