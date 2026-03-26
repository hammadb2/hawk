"""Breach Check router — check staff emails against HaveIBeenPwned."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator

from backend.auth import get_current_user
from backend.config import HIBP_API_KEY
from backend.models import User
from backend.services.hibp import check_domain_emails

router = APIRouter(tags=["breach-check"])

MAX_EMAILS = 50  # guard against abuse


class BreachCheckRequest(BaseModel):
    domain: str
    emails: list[EmailStr]

    @field_validator("emails")
    @classmethod
    def limit_emails(cls, v: list) -> list:
        if not v:
            raise ValueError("Provide at least one email address")
        if len(v) > MAX_EMAILS:
            raise ValueError(f"Maximum {MAX_EMAILS} emails per request")
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Domain must not be empty")
        return v


class BreachEntry(BaseModel):
    name: str
    title: str
    breach_date: str
    data_classes: list[str]
    is_verified: bool
    pwn_count: int


class EmailBreachResult(BaseModel):
    email: str
    breached: bool
    breach_count: int
    breaches: list[BreachEntry]
    error: str | None = None


class BreachCheckResponse(BaseModel):
    domain: str
    total_checked: int
    breached_count: int
    clean_count: int
    results: list[EmailBreachResult]


@router.post("/api/breach-check", response_model=BreachCheckResponse)
def breach_check(
    req: BreachCheckRequest,
    user: User = Depends(get_current_user),
):
    """
    Check a list of staff email addresses against HaveIBeenPwned.
    Returns per-email breach details and domain-level summary.
    Requires a valid HIBP_API_KEY in server config.
    """
    if not HIBP_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Breach check is not configured on this server (missing HIBP_API_KEY).",
        )

    # Validate emails belong to the stated domain
    domain = req.domain
    invalid = [e for e in req.emails if not e.lower().endswith(f"@{domain}")]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"All emails must belong to domain '{domain}'. "
                   f"Invalid: {', '.join(invalid[:5])}",
        )

    raw_results = check_domain_emails(list(req.emails))

    results = [EmailBreachResult(**r) for r in raw_results]
    breached_count = sum(1 for r in results if r.breached)

    return BreachCheckResponse(
        domain=domain,
        total_checked=len(results),
        breached_count=breached_count,
        clean_count=len(results) - breached_count,
        results=results,
    )
