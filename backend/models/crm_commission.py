"""CRM Commission — closing and residual commissions earned by reps."""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base

COMMISSION_CLOSING = "closing"
COMMISSION_RESIDUAL = "residual"


class CRMCommission(Base):
    __tablename__ = "crm_commissions"

    id = Column(String(36), primary_key=True)
    crm_user_id = Column(String(36), ForeignKey("crm_users.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(String(36), ForeignKey("crm_clients.id", ondelete="CASCADE"), nullable=False)
    commission_type = Column(String(20), nullable=False)  # closing or residual
    amount = Column(Integer, nullable=False)  # in cents
    period_start = Column(Date, nullable=True)   # for residual: month start
    period_end = Column(Date, nullable=True)     # for residual: month end
    paid = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    crm_user = relationship("CRMUser", back_populates="commissions")
    client = relationship("CRMClient", back_populates="commissions")
