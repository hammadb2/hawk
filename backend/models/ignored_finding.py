from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from database import Base


class IgnoredFinding(Base):
    __tablename__ = "ignored_findings"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    finding_id = Column(String(36), nullable=False, index=True)  # UUID from scanner
    scan_id = Column(String(36), ForeignKey("scans.id"), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
