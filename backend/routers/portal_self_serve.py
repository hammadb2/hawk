"""Account-first portal: bootstrap CRM rows before payment."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid_and_email
from services.portal_bootstrap import bootstrap_portal_account
from services.portal_first_login import mark_first_portal_login
from services.portal_incident_report import report_incident
from services.portal_primary_domain import set_portal_primary_domain

router = APIRouter(prefix="/api/portal", tags=["portal"])


class PrimaryDomainBody(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)


class IncidentReportBody(BaseModel):
    description: str = Field(default="", max_length=4000)


@router.post("/bootstrap")
def post_portal_bootstrap(auth: tuple[str, str] = Depends(require_supabase_uid_and_email)):
    """Create clients + client_portal_profiles for signed-in user if missing (idempotent)."""
    uid, email = auth
    return bootstrap_portal_account(uid, email)


@router.post("/primary-domain")
def post_primary_domain(
    body: PrimaryDomainBody,
    auth: tuple[str, str] = Depends(require_supabase_uid_and_email),
):
    """Set the monitored apex domain (required when sign-up email is a generic provider)."""
    uid, _email = auth
    return set_portal_primary_domain(uid, body.domain)


@router.post("/mark-first-login-seen")
def post_mark_first_login_seen(auth: tuple[str, str] = Depends(require_supabase_uid_and_email)):
    """Stamp ``clients.last_portal_login_at`` for priority list #32.

    Called from ``/portal/welcome`` on mount. PortalGate uses the
    column's null-ness to decide whether to route first-time visitors
    into the welcome view, so writing this timestamp is what retires
    the one-shot redirect for this account.
    """
    uid, _email = auth
    return mark_first_portal_login(uid)


@router.post("/incident-report")
def post_incident_report(
    body: IncidentReportBody,
    auth: tuple[str, str] = Depends(require_supabase_uid_and_email),
):
    """Client-initiated incident / breach report (priority list #34).

    Logs a row in ``client_incident_reports`` with an SLA clock,
    SMS-pages the CEO via OpenPhone, emails the client a confirmation
    via Resend, and mirrors the event into ``crm_support_tickets`` for
    internal ops. Each fan-out step is best-effort — the incident is
    still persisted if any of them fail.
    """
    uid, email = auth
    return report_incident(uid=uid, user_email=email, description=body.description or "")
