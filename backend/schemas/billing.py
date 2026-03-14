from __future__ import annotations

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern=r"^(starter|pro|agency)$")


class InvoiceItem(BaseModel):
    id: str
    amount_due: int
    amount_paid: int
    status: str
    created: int
    pdf_url: str | None = None
