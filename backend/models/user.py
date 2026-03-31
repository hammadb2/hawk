from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    company = Column(String(255), nullable=True)
    industry = Column(String(100), nullable=True)
    province = Column(String(100), nullable=True)
    plan = Column(String(50), nullable=False, default="trial")  # trial, starter, pro, agency
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    domains = relationship("Domain", back_populates="user")
    scans = relationship("Scan", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    reports = relationship("Report", back_populates="user")
