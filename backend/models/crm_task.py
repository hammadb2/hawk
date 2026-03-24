"""CRM Task — follow-up task assigned to a rep for a prospect."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base

PRIORITY_LOW = "low"
PRIORITY_MEDIUM = "medium"
PRIORITY_HIGH = "high"


class CRMTask(Base):
    __tablename__ = "crm_tasks"

    id = Column(String(36), primary_key=True)
    crm_user_id = Column(String(36), ForeignKey("crm_users.id", ondelete="CASCADE"), nullable=False)
    prospect_id = Column(String(36), ForeignKey("crm_prospects.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    priority = Column(String(10), nullable=False, default=PRIORITY_MEDIUM)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    crm_user = relationship("CRMUser", back_populates="tasks")
    prospect = relationship("CRMProspect", back_populates="tasks")
