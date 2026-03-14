from __future__ import annotations

from pydantic import BaseModel, Field


class AgencyClientCreate(BaseModel):
    name: str = Field(..., min_length=1)
    email: str | None = None
    company: str | None = None


class AgencyClientResponse(BaseModel):
    id: str
    user_id: str
    name: str
    email: str | None
    company: str | None
    created_at: str

    class Config:
        from_attributes = True
