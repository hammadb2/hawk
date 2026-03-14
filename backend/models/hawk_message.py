from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from backend.database import Base


class HawkMessage(Base):
    """Tracks Ask HAWK message count per user (for trial limit)."""
    __tablename__ = "hawk_messages"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    message_count = Column(Integer, default=0)
    period_start = Column(DateTime(timezone=True), default=datetime.utcnow)  # reset each billing period or trial
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
