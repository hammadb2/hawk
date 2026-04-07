"""Account-first portal: bootstrap CRM rows before payment."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routers.crm_auth import require_supabase_uid_and_email
from services.portal_bootstrap import bootstrap_portal_account

router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.post("/bootstrap")
def post_portal_bootstrap(auth: tuple[str, str] = Depends(require_supabase_uid_and_email)):
    """Create clients + client_portal_profiles for signed-in user if missing (idempotent)."""
    uid, email = auth
    return bootstrap_portal_account(uid, email)
