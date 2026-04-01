"""CRM — Stripe payment verification for close-won."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid
from services.crm_stripe_crm import verify_payment_recent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm", tags=["crm-payment"])


class VerifyPaymentBody(BaseModel):
    domain: str = Field(..., min_length=2)
    mrr_cents: int = Field(..., ge=0)
    stripe_customer_id: str | None = None


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
