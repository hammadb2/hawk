"""CRM Charlotte Email — automated outreach email log."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base

EMAIL_STATUS_SENT = "sent"
EMAIL_STATUS_DELIVERED = "delivered"
EMAIL_STATUS_OPENED = "opened"
EMAIL_STATUS_REPLIED = "replied"
EMAIL_STATUS_BOUNCED = "bounced"


class CRMCharlotteEmail(Base):
    __tablename__ = "crm_charlotte_emails"

    id = Column(String(36), primary_key=True)
    prospect_id = Column(String(36), ForeignKey("crm_prospects.id", ondelete="CASCADE"), nullable=False)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=True)
    body = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default=EMAIL_STATUS_SENT)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    prospect = relationship("CRMProspect", back_populates="charlotte_emails")
