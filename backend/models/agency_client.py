from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from database import Base


class AgencyClient(Base):
    __tablename__ = "agency_clients"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)  # agency user
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
