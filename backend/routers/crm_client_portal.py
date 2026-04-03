"""CRM — provision client portal after close-won (Supabase invite + role=client)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routers.crm_auth import require_supabase_uid
from services.crm_client_portal_provision import assert_crm_staff_can_provision, provision_portal_for_client

router = APIRouter(prefix="/api/crm", tags=["crm-client-portal"])


@router.post("/clients/{client_id}/provision-portal")
def post_provision_client_portal(
    client_id: str,
    uid: str = Depends(require_supabase_uid),
):
    """
    Called after prospects → clients insert on Close Won.
    Invites contact_email to the portal (magic link), sets profiles.role=client, links client_portal_profiles.
    """
    assert_crm_staff_can_provision(uid)
    return provision_portal_for_client(client_id)
