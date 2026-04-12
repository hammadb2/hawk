"""CRM — Stripe payment verification for close-won + commission payout management."""

from __future__ import annotations

import logging
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid
from services.crm_stripe_crm import verify_payment_recent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm", tags=["crm-payment"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _require_exec_role(uid: str) -> None:
    """Only CEO or HoS can manage commission payouts."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "role", "limit": "1"},
        timeout=15.0,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows or rows[0].get("role") not in ("ceo", "hos"):
        raise HTTPException(status_code=403, detail="Only CEO or HoS can manage commission payouts")


class VerifyPaymentBody(BaseModel):
    domain: str = Field(..., min_length=2)
    mrr_cents: int = Field(..., ge=0)
    stripe_customer_id: str | None = None


class UpdateCommissionBody(BaseModel):
    status: Literal["pending", "approved", "paid"]


@router.post("/verify-payment")
def verify_payment(body: VerifyPaymentBody, uid: str = Depends(require_supabase_uid)):
    """Returns whether Stripe shows a matching successful payment in the last 24h."""
    _ = uid
    ok = verify_payment_recent(
        domain=body.domain.strip(),
        mrr_cents=body.mrr_cents,
        stripe_customer_id=(body.stripe_customer_id or "").strip() or None,
    )
    return {"verified": ok}


@router.patch("/commissions/bulk-update")
def bulk_update_commission_status(
    body: UpdateCommissionBody,
    uid: str = Depends(require_supabase_uid),
):
    """CEO/HoS bulk-updates all pending commissions to approved, or all approved to paid."""
    _require_exec_role(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Determine which commissions to update based on target status
    if body.status == "approved":
        source_status = "pending"
    elif body.status == "paid":
        source_status = "approved"
    else:
        raise HTTPException(status_code=400, detail="Bulk update only supports pending→approved or approved→paid")

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/crm_commissions",
        headers=_sb_headers(),
        params={"status": f"eq.{source_status}"},
        json={"status": body.status},
        timeout=30.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text[:400])

    updated = r.json() if r.text.strip() else []
    return {"ok": True, "updated_count": len(updated) if isinstance(updated, list) else 0}


@router.patch("/commissions/{commission_id}")
def update_commission_status(
    commission_id: str,
    body: UpdateCommissionBody,
    uid: str = Depends(require_supabase_uid),
):
    """CEO/HoS updates a commission status (pending → approved → paid)."""
    _require_exec_role(uid)
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Verify commission exists
    check = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_commissions",
        headers=_sb_headers(),
        params={"id": f"eq.{commission_id}", "select": "id,status", "limit": "1"},
        timeout=15.0,
    )
    check.raise_for_status()
    rows = check.json()
    if not rows:
        raise HTTPException(status_code=404, detail="Commission not found")

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/crm_commissions",
        headers=_sb_headers(),
        params={"id": f"eq.{commission_id}"},
        json={"status": body.status},
        timeout=15.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text[:400])

    updated = r.json()
    return {"ok": True, "commission": updated[0] if updated else None}
