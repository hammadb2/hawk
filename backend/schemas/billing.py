from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern=r"^(starter|pro|agency)$")


class PublicCheckoutRequest(BaseModel):
    """Marketing site — pay before account exists. Webhook reads metadata.hawk_product."""

    hawk_product: Literal["starter", "shield"] = Field(..., description="starter ($199) or shield ($997)")


class CheckoutCompleteRequest(BaseModel):
    """Hosted checkout: session_id. Embedded Elements: subscription_id (+ optional email/name for verification)."""

    session_id: str | None = Field(None, description="Stripe Checkout Session id (cs_...)")
    subscription_id: str | None = Field(None, description="Stripe Subscription id (sub_...) after embedded payment")
    email: str | None = Field(None, description="Optional; must match Stripe customer when using subscription_id")
    name: str | None = None
    hawk_product: Literal["starter", "shield"] | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "CheckoutCompleteRequest":
        if self.session_id and self.subscription_id:
            raise ValueError("Provide either session_id or subscription_id, not both")
        if not self.session_id and not self.subscription_id:
            raise ValueError("Provide session_id or subscription_id")
        return self


class CreatePaymentIntentRequest(BaseModel):
    """Embedded checkout — create incomplete subscription + PaymentIntent client_secret."""

    email: str = Field(..., min_length=3, max_length=320)
    name: str = Field(..., min_length=1, max_length=200)
    hawk_product: Literal["starter", "shield"] = "shield"
    test_mode: bool = False
    # Set by portal route so checkout-complete finds the right CRM row (domain is not unique for gmail.com, etc.)
    crm_client_id: str | None = Field(None, description="public.clients id from bootstrap")


class CreatePaymentIntentPortalRequest(BaseModel):
    """Same as embedded checkout but email comes from Supabase JWT (signed-in portal user)."""

    name: str | None = Field(None, max_length=200)
    hawk_product: Literal["starter", "shield"] = "shield"
    test_mode: bool = False


class InvoiceItem(BaseModel):
    id: str
    amount_due: int
    amount_paid: int
    status: str
    created: int
    pdf_url: str | None = None
