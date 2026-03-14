from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class Domain(Base):
    __tablename__ = "domains"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    domain = Column(String(255), nullable=False, index=True)
    label = Column(String(255), nullable=True)
    scan_frequency = Column(String(50), nullable=True)  # on_demand, weekly, daily
    notify_email = Column(String(255), nullable=True)
    notify_slack = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    user = relationship("User", back_populates="domains")
    scans = relationship("Scan", back_populates="domain")
