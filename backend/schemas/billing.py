from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern=r"^(starter|pro|agency)$")


class PublicCheckoutRequest(BaseModel):
    """Marketing site — pay before account exists. Webhook reads metadata.hawk_product."""

    hawk_product: Literal["starter", "shield"] = Field(..., description="starter ($199) or shield ($997)")


class InvoiceItem(BaseModel):
    id: str
    amount_due: int
    amount_paid: int
    status: str
    created: int
    pdf_url: str | None = None
