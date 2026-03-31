from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Scan(Base):
    __tablename__ = "scans"

    id = Column(String(36), primary_key=True)
    domain_id = Column(String(36), ForeignKey("domains.id"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    scanned_domain = Column(String(255), nullable=True)  # domain string when no Domain record
    triggered_by = Column(String(50), nullable=True)  # user, schedule, api
    status = Column(String(50), nullable=False, default="pending")  # pending, running, completed, failed
    score = Column(Integer, nullable=True)
    grade = Column(String(5), nullable=True)
    findings_json = Column(Text, nullable=True)  # JSON array of findings
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="scans")
    domain = relationship("Domain", back_populates="scans")
