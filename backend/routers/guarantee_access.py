"""Gated Breach Response Guarantee document — email verification + JWT (public)."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from auth import create_access_token, get_guarantee_doc_email
from config import SECRET_KEY
from services.crm_portal_email import send_guarantee_verification_code_email

logger = logging.getLogger(__name__)

router = APIRouter(tags=["guarantee"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

DOC_PATH = Path(__file__).resolve().parent.parent / "content" / "guarantee_breach_response.md"
CODE_TTL_MIN = 15
JWT_DAYS = 7


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _hash_code(email: str, code: str) -> str:
    raw = f"{email.lower().strip()}:{code.strip()}:{SECRET_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _norm_email(v: str) -> str:
    return v.lower().strip()


def _generate_code() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


def _load_markdown() -> str:
    if not DOC_PATH.is_file():
        logger.error("guarantee document missing: %s", DOC_PATH)
        return "# Document unavailable\n\nPlease contact hello@securedbyhawk.com."
    return DOC_PATH.read_text(encoding="utf-8")


class RequestCodeBody(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=200)
    company: str = Field(..., min_length=1, max_length=200)


class VerifyBody(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)


@router.post("/api/guarantee/request-code")
def guarantee_request_code(body: RequestCodeBody) -> dict[str, str]:
    if not SUPABASE_URL or not SERVICE_KEY:
        logger.error("guarantee request-code: Supabase not configured")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    email = _norm_email(str(body.email))
    code = _generate_code()
    h = _hash_code(email, code)
    exp = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MIN)

    try:
        httpx.delete(
            f"{SUPABASE_URL}/rest/v1/guarantee_verification_codes",
            headers=_sb_headers(),
            params={"email": f"eq.{email}"},
            timeout=20.0,
        )
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/guarantee_verification_codes",
            headers=_sb_headers(),
            json={
                "email": email,
                "full_name": body.name.strip()[:200],
                "company": body.company.strip()[:200],
                "code_hash": h,
                "expires_at": exp.isoformat(),
            },
            timeout=20.0,
        ).raise_for_status()
    except Exception:
        logger.exception("guarantee request-code: Supabase failed email=%s", email)
        raise HTTPException(status_code=503, detail="Could not send verification. Try again shortly.")

    try:
        send_guarantee_verification_code_email(to_email=email, code=code, full_name=body.name.strip())
    except Exception:
        logger.exception("guarantee request-code: Resend failed email=%s", email)
        raise HTTPException(status_code=503, detail="Could not send email. Try again shortly.")

    return {"ok": "true"}


@router.post("/api/guarantee/verify")
def guarantee_verify(body: VerifyBody) -> dict[str, str]:
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    email = _norm_email(str(body.email))
    digits = re.sub(r"\D", "", body.code)
    if len(digits) != 6:
        raise HTTPException(status_code=400, detail="Enter the 6-digit code from your email.")

    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/guarantee_verification_codes",
            headers=_sb_headers(),
            params={
                "email": f"eq.{email}",
                "select": "id,code_hash,expires_at",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json() or []
    except Exception:
        logger.exception("guarantee verify: read failed email=%s", email)
        raise HTTPException(status_code=503, detail="Verification failed. Try again.")

    if not rows:
        raise HTTPException(status_code=400, detail="No code found for this email. Request a new code.")

    row = rows[0]
    exp = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Code expired. Request a new code.")

    h = _hash_code(email, digits)
    if not secrets.compare_digest(h, row["code_hash"]):
        raise HTTPException(status_code=400, detail="Invalid code. Check the email from noreply@securedbyhawk.com.")

    try:
        httpx.delete(
            f"{SUPABASE_URL}/rest/v1/guarantee_verification_codes",
            headers=_sb_headers(),
            params={"id": f"eq.{row['id']}"},
            timeout=20.0,
        ).raise_for_status()
    except Exception:
        logger.exception("guarantee verify: delete row failed id=%s", row.get("id"))

    token = create_access_token(
        {
            "sub": "guarantee_doc_access",
            "email": email,
            "typ": "guarantee_doc",
        },
        expires_delta=timedelta(days=JWT_DAYS),
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/api/guarantee/document")
def guarantee_document(_email: str = Depends(get_guarantee_doc_email)) -> dict[str, str]:
    return {"markdown": _load_markdown()}
