"""CRM Activity — logged interaction on a prospect (call, email, note, stage change, etc.)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base

ACTIVITY_CALL = "call"
ACTIVITY_EMAIL = "email"
ACTIVITY_NOTE = "note"
ACTIVITY_STAGE_CHANGE = "stage_change"
ACTIVITY_LOOM = "loom"
ACTIVITY_MEETING = "meeting"

ALL_ACTIVITY_TYPES = [
    ACTIVITY_CALL,
    ACTIVITY_EMAIL,
    ACTIVITY_NOTE,
    ACTIVITY_STAGE_CHANGE,
    ACTIVITY_LOOM,
    ACTIVITY_MEETING,
]


class CRMActivity(Base):
    __tablename__ = "crm_activities"

    id = Column(String(36), primary_key=True)
    prospect_id = Column(String(36), ForeignKey("crm_prospects.id", ondelete="CASCADE"), nullable=False)
    crm_user_id = Column(String(36), ForeignKey("crm_users.id", ondelete="SET NULL"), nullable=True)  # NULL for Charlotte
    activity_type = Column(String(30), nullable=False)
    description = Column(Text, nullable=True)
    old_stage = Column(String(30), nullable=True)  # only for stage_change
    new_stage = Column(String(30), nullable=True)  # only for stage_change
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    prospect = relationship("CRMProspect", back_populates="activities")
    crm_user = relationship("CRMUser", back_populates="activities")
