"""SQLAlchemy ORM models for the HAWK Pulse state engine."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MonitoredDomain(Base):
    """A domain registered for continuous monitoring."""

    __tablename__ = "monitored_domains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    owner_email: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assets: Mapped[list[Asset]] = relationship("Asset", back_populates="domain_rel", cascade="all, delete-orphan")


class Asset(Base):
    """
    A discovered asset (subdomain, IP, port, certificate) tied to a monitored domain.
    The state engine diffs against this table to detect changes.
    """

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitored_domains.id"), nullable=False)
    asset_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="subdomain | open_port | certificate | http_service",
    )
    asset_key: Mapped[str] = mapped_column(
        String(512), nullable=False,
        comment="Unique identifier within type, e.g. 'api.example.com:443' or cert fingerprint",
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    domain_rel: Mapped[MonitoredDomain] = relationship("MonitoredDomain", back_populates="assets")

    __table_args__ = (
        Index("ix_assets_domain_type_key", "domain_id", "asset_type", "asset_key", unique=True),
    )


class Alert(Base):
    """A state-change alert: something appeared, disappeared, or changed."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitored_domains.id"), nullable=False)
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="new_asset | asset_gone | cert_issued | port_opened | port_closed",
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    remediation_markdown: Mapped[str | None] = mapped_column(Text, comment="AI-generated fix guide (Markdown)")
    remediation_status: Mapped[str | None] = mapped_column(
        String(20), comment="pending | generating | complete | failed"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_alerts_domain_created", "domain_id", "created_at"),
    )


class ScanEvent(Base):
    """Audit log of every micro-scan triggered by a listener."""

    __tablename__ = "scan_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitored_domains.id"), nullable=False)
    trigger: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="certstream | scheduled | manual",
    )
    trigger_detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result_summary: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
