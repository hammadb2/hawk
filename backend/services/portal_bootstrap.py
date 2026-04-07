"""Self-serve portal: ensure CRM client + portal profile exist before payment (account-first)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException

from config import SUPABASE_URL
from services.crm_profile_sync import ensure_client_profile

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def bootstrap_portal_account(uid: str, email: str) -> dict[str, Any]:
    """
    Idempotent: create or link clients + client_portal_profiles for magic-link users.
    billing_status stays pending_payment until Stripe checkout-complete / webhook.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    em = email.strip().lower()
    if "@" not in em:
        raise HTTPException(status_code=400, detail="Invalid email")

    domain = em.split("@", 1)[1].strip().lower()
    company = em.split("@", 1)[0].replace(".", " ").replace("_", " ").title()[:200]

    # Already linked?
    r_cpp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_headers(),
        params={"user_id": f"eq.{uid}", "select": "id,client_id", "limit": "1"},
        timeout=20.0,
    )
    r_cpp.raise_for_status()
    cpp_rows = r_cpp.json()
    if cpp_rows:
        return {"ok": True, "client_id": str(cpp_rows[0]["client_id"]), "created": False}

    r_cl = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={"domain": f"eq.{domain}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    r_cl.raise_for_status()
    cl_rows = r_cl.json()

    if not cl_rows:
        ins = httpx.post(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=_headers(),
            params={"select": "*"},
            json={
                "company_name": company,
                "domain": domain,
                "plan": "hawk_shield",
                "mrr_cents": 0,
                "status": "active",
                "portal_user_id": uid,
                "billing_status": "pending_payment",
            },
            timeout=20.0,
        )
        if ins.status_code >= 400:
            logger.error("bootstrap clients insert: %s %s", ins.status_code, ins.text[:500])
            raise HTTPException(status_code=502, detail="Could not create client record") from None
        out = ins.json()
        row = out[0] if isinstance(out, list) and out else out
        if not isinstance(row, dict) or not row.get("id"):
            raise HTTPException(status_code=502, detail="Unexpected clients insert response")
        cid = str(row["id"])
        cpp = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
            headers=_headers(),
            params={"select": "*"},
            json={
                "user_id": uid,
                "client_id": cid,
                "email": em,
                "company_name": company,
                "domain": domain,
            },
            timeout=20.0,
        )
        if cpp.status_code >= 400:
            logger.error("bootstrap cpp insert: %s %s", cpp.status_code, cpp.text[:500])
            raise HTTPException(status_code=502, detail="Could not create portal profile") from None
        try:
            ensure_client_profile(uid, em, company)
        except Exception:
            logger.exception("bootstrap ensure_client_profile")
            raise HTTPException(status_code=502, detail="Could not ensure user profile") from None
        return {"ok": True, "client_id": cid, "created": True}

    cl = cl_rows[0]
    cid = str(cl.get("id"))
    puid = cl.get("portal_user_id")
    if puid and str(puid) != uid:
        raise HTTPException(
            status_code=409,
            detail="This organization already has a different portal user. Contact support.",
        )

    if not puid:
        patch = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=_headers(),
            params={"id": f"eq.{cid}"},
            json={"portal_user_id": uid},
            timeout=20.0,
        )
        if patch.status_code >= 400:
            logger.error("bootstrap portal_user_id patch: %s %s", patch.status_code, patch.text[:400])
            raise HTTPException(status_code=502, detail="Could not link portal user") from None

    r_existing_cpp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_headers(),
        params={"client_id": f"eq.{cid}", "select": "id,user_id", "limit": "1"},
        timeout=20.0,
    )
    r_existing_cpp.raise_for_status()
    ecpp = r_existing_cpp.json()
    if ecpp:
        existing_uid = ecpp[0].get("user_id")
        if existing_uid and str(existing_uid) != uid:
            raise HTTPException(
                status_code=409,
                detail="This organization is already linked to another portal login.",
            )
        return {"ok": True, "client_id": cid, "created": False}

    cpp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_headers(),
        params={"select": "*"},
        json={
            "user_id": uid,
            "client_id": cid,
            "email": em,
            "company_name": cl.get("company_name") or company,
            "domain": domain,
        },
        timeout=20.0,
    )
    if cpp.status_code >= 400:
        logger.error("bootstrap cpp insert (existing client): %s %s", cpp.status_code, cpp.text[:500])
        raise HTTPException(status_code=502, detail="Could not create portal profile") from None
    try:
        ensure_client_profile(uid, em, company)
    except Exception:
        logger.exception("bootstrap ensure_client_profile (existing client)")
        raise HTTPException(status_code=502, detail="Could not ensure user profile") from None
    return {"ok": True, "client_id": cid, "created": True}
