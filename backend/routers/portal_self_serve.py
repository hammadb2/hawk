"""Account-first portal: bootstrap CRM rows before payment."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid_and_email
from services.portal_bootstrap import bootstrap_portal_account
from services.portal_primary_domain import set_portal_primary_domain

router = APIRouter(prefix="/api/portal", tags=["portal"])


class PrimaryDomainBody(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)


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
