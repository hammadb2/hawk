from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, String

from database import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token = Column(String(64), primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
