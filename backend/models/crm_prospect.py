"""CRM Prospect — a company being worked through the sales pipeline."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base

STAGE_NEW = "new"
STAGE_SCANNED = "scanned"
STAGE_LOOM_SENT = "loom_sent"
STAGE_REPLIED = "replied"
STAGE_CALL_BOOKED = "call_booked"
STAGE_PROPOSAL_SENT = "proposal_sent"
STAGE_CLOSED_WON = "closed_won"
STAGE_CLOSED_LOST = "closed_lost"

PIPELINE_STAGES = [
    STAGE_NEW,
    STAGE_SCANNED,
    STAGE_LOOM_SENT,
    STAGE_REPLIED,
    STAGE_CALL_BOOKED,
    STAGE_PROPOSAL_SENT,
    STAGE_CLOSED_WON,
    STAGE_CLOSED_LOST,
]

SOURCE_CHARLOTTE = "charlotte"
SOURCE_MANUAL = "manual"
SOURCE_CSV_IMPORT = "csv_import"
SOURCE_REFERRAL = "referral"


class CRMProspect(Base):
    __tablename__ = "crm_prospects"

    id = Column(String(36), primary_key=True)
    company_name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    industry = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    stage = Column(String(30), nullable=False, default=STAGE_NEW)
    hawk_score = Column(Integer, nullable=True)  # 0-100, null until scanned
    assigned_rep_id = Column(String(36), ForeignKey("crm_users.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(50), nullable=False, default=SOURCE_MANUAL)
    notes = Column(Text, nullable=True)
    estimated_mrr = Column(Integer, nullable=True)  # in cents
    lost_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assigned_rep = relationship("CRMUser", foreign_keys=[assigned_rep_id], back_populates="prospects")
    activities = relationship("CRMActivity", back_populates="prospect", cascade="all, delete-orphan", order_by="CRMActivity.created_at.desc()")
    tasks = relationship("CRMTask", back_populates="prospect", cascade="all, delete-orphan")
    charlotte_emails = relationship("CRMCharlotteEmail", back_populates="prospect", cascade="all, delete-orphan")
    client = relationship("CRMClient", back_populates="prospect", uselist=False)
