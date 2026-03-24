"""CRM User — internal sales rep profile linked to the main User account."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base

CRM_ROLE_CEO = "ceo"
CRM_ROLE_HEAD_OF_SALES = "head_of_sales"
CRM_ROLE_TEAM_LEAD = "team_lead"
CRM_ROLE_SALES_REP = "sales_rep"
CRM_ROLE_CHARLOTTE = "charlotte"

ALL_CRM_ROLES = [
    CRM_ROLE_CEO,
    CRM_ROLE_HEAD_OF_SALES,
    CRM_ROLE_TEAM_LEAD,
    CRM_ROLE_SALES_REP,
    CRM_ROLE_CHARLOTTE,
]


class CRMUser(Base):
    __tablename__ = "crm_users"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    crm_role = Column(String(20), nullable=False)  # see constants above
    monthly_target = Column(Integer, nullable=False, default=0)  # dollars
    team_lead_id = Column(String(36), ForeignKey("crm_users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    team_lead = relationship("CRMUser", remote_side="CRMUser.id", foreign_keys=[team_lead_id])
    team_members = relationship("CRMUser", foreign_keys=[team_lead_id], back_populates="team_lead", overlaps="team_lead")
    prospects = relationship("CRMProspect", foreign_keys="CRMProspect.assigned_rep_id", back_populates="assigned_rep")
    clients_closed = relationship("CRMClient", foreign_keys="CRMClient.closed_by_rep_id", back_populates="closed_by_rep")
    tasks = relationship("CRMTask", foreign_keys="CRMTask.crm_user_id", back_populates="crm_user")
    commissions = relationship("CRMCommission", foreign_keys="CRMCommission.crm_user_id", back_populates="crm_user")
    activities = relationship("CRMActivity", foreign_keys="CRMActivity.crm_user_id", back_populates="crm_user")
