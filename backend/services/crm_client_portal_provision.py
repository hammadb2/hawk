"""Provision Supabase Auth + client_portal_profiles + profiles.role=client after CRM close-won."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException

from config import SUPABASE_URL
from services.crm_portal_stripe import _invite_portal_user, _lookup_user_id_by_email

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _staff_roles() -> frozenset[str]:
    return frozenset({"ceo", "hos", "team_lead", "sales_rep", "closer"})


def assert_crm_staff_can_provision(actor_uid: str) -> None:
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"id": f"eq.{actor_uid}", "select": "role", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise HTTPException(status_code=403, detail="CRM profile not found for caller")
    role = (rows[0].get("role") or "").lower()
    if role == "client":
        raise HTTPException(status_code=403, detail="Client accounts cannot provision portal")
    if role not in _staff_roles():
        raise HTTPException(status_code=403, detail="Insufficient role to provision portal")


def _profile_role(uid: str) -> str | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"id": f"eq.{uid}", "select": "role", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    return (rows[0].get("role") or "").lower() or None


def provision_portal_for_client(client_id: str) -> dict[str, Any]:
    """
    Invite contact email, set profiles.role=client, link client_portal_profiles and clients.portal_user_id.
    Idempotent if already provisioned.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={
            "id": f"eq.{client_id}",
            "select": "id,company_name,domain,portal_user_id,prospect_id",
            "limit": "1",
        },
        timeout=20.0,
    )
    cr.raise_for_status()
    crows = cr.json()
    if not crows:
        raise HTTPException(status_code=404, detail="Client not found")
    client = crows[0]
    pid = client.get("prospect_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Client has no prospect_id")

    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_headers(),
        params={"id": f"eq.{pid}", "select": "contact_email,company_name,domain", "limit": "1"},
        timeout=20.0,
    )
    pr.raise_for_status()
    pros = pr.json()
    if not pros:
        raise HTTPException(status_code=400, detail="Prospect not found")
    email = (pros[0].get("contact_email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Prospect has no valid contact_email — add it before close won")

    company = (client.get("company_name") or pros[0].get("company_name") or pros[0].get("domain") or "Client")[:200]

    if client.get("portal_user_id"):
        uid = str(client["portal_user_id"])
        role = _profile_role(uid)
        if role and role in _staff_roles():
            raise HTTPException(
                status_code=409,
                detail="Portal user id is linked to a CRM staff profile — fix profiles.role or portal linkage manually.",
            )
        _ensure_profile_client(uid, email, company)
        _ensure_cpp_and_patch(uid, client_id, email, company, client.get("domain") or pros[0].get("domain"))
        return {"ok": True, "idempotent": True, "portal_user_id": uid}

    uid = _invite_portal_user(email=email, company_name=str(company), client_id=client_id)
    if not uid:
        uid = _lookup_user_id_by_email(email)
    if not uid:
        raise HTTPException(status_code=502, detail="Could not create or resolve auth user for portal invite")

    role = _profile_role(uid)
    if role and role in _staff_roles():
        raise HTTPException(
            status_code=409,
            detail="This contact email is already a CRM team account. Use a client-only email for the portal.",
        )

    _ensure_profile_client(uid, email, company)
    _ensure_cpp_and_patch(uid, client_id, email, company, client.get("domain") or pros[0].get("domain"))

    return {"ok": True, "portal_user_id": uid, "invited_email": email}


def _ensure_profile_client(uid: str, email: str, company: str) -> None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_headers(),
        params={"id": f"eq.{uid}", "select": "id,role", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    body = {"role": "client", "status": "active", "email": email, "full_name": company[:120]}
    if not rows:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_headers(),
            json={"id": uid, **body},
            timeout=20.0,
        ).raise_for_status()
    else:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_headers(),
            params={"id": f"eq.{uid}"},
            json=body,
            timeout=20.0,
        ).raise_for_status()


def _ensure_cpp_and_patch(
    uid: str,
    client_id: str,
    email: str,
    company: str,
    domain: str | None,
) -> None:
    cpp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_headers(),
        params={"client_id": f"eq.{client_id}", "select": "id", "limit": "1"},
        timeout=20.0,
    )
    cpp.raise_for_status()
    if not cpp.json():
        ins = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
            headers=_headers(),
            json={
                "user_id": uid,
                "client_id": client_id,
                "email": email,
                "company_name": company,
                "domain": domain,
            },
            timeout=20.0,
        )
        if ins.status_code >= 400:
            logger.error("client_portal_profiles insert failed: %s", ins.text[:400])
            ins.raise_for_status()

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={"id": f"eq.{client_id}"},
        json={
            "portal_user_id": uid,
            "onboarding_sequence_status": "in_progress",
        },
        timeout=20.0,
    ).raise_for_status()
