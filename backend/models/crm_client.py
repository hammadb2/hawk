"""CRM Client — a prospect that has been converted (closed won)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base

CHURN_RISK_LOW = "low"
CHURN_RISK_MEDIUM = "medium"
CHURN_RISK_HIGH = "high"

CLIENT_STATUS_ACTIVE = "active"
CLIENT_STATUS_CHURNED = "churned"


class CRMClient(Base):
    __tablename__ = "crm_clients"

    id = Column(String(36), primary_key=True)
    prospect_id = Column(String(36), ForeignKey("crm_prospects.id", ondelete="SET NULL"), unique=True, nullable=True)
    company_name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    mrr = Column(Integer, nullable=False)  # in cents
    closed_by_rep_id = Column(String(36), ForeignKey("crm_users.id", ondelete="SET NULL"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    churn_risk = Column(String(20), nullable=False, default=CHURN_RISK_LOW)
    churn_risk_reason = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default=CLIENT_STATUS_ACTIVE)
    churned_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    prospect = relationship("CRMProspect", back_populates="client")
    closed_by_rep = relationship("CRMUser", foreign_keys=[closed_by_rep_id], back_populates="clients_closed")
    commissions = relationship("CRMCommission", back_populates="client", cascade="all, delete-orphan")
