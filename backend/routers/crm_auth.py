"""Shared Supabase JWT verification for CRM FastAPI routes."""

from __future__ import annotations

import logging

import httpx
from fastapi import Header, HTTPException
from jose import JWTError, jwt

from config import SUPABASE_JWT_SECRET, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

_JWT_OPTIONS = {"leeway": 30}


def _verify_supabase_user_via_rest(token: str) -> dict:
    """
    Validate access token via Supabase Auth (GET /auth/v1/user).
    Use when local HS256 decode fails (wrong SUPABASE_JWT_SECRET on Railway, secret rotation, etc.).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")
    r = httpx.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
        },
        timeout=15.0,
    )
    if r.status_code != 200:
        logger.warning("auth/v1/user failed: %s %s", r.status_code, (r.text or "")[:300])
        raise HTTPException(status_code=401, detail="Invalid token")
    user = r.json()
    uid = user.get("id")
    email = (user.get("email") or "").strip().lower()
    if not uid or not isinstance(uid, str):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {"sub": uid, "email": email}


def _decode_supabase_bearer(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    if SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options=_JWT_OPTIONS,
            )
        except JWTError:
            try:
                return jwt.decode(
                    token,
                    SUPABASE_JWT_SECRET,
                    algorithms=["HS256"],
                    options={"verify_aud": False, **_JWT_OPTIONS},
                )
            except JWTError as e:
                logger.warning("jwt decode failed (will try Supabase Auth API): %s", e)

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        return _verify_supabase_user_via_rest(token)

    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=503, detail="SUPABASE_JWT_SECRET not configured on API")
    raise HTTPException(status_code=401, detail="Invalid token")


def require_supabase_uid(authorization: str | None = Header(default=None)) -> str:
    """Bearer access token from Supabase Auth (anon sign-in). Returns auth.users id."""
    payload = _decode_supabase_bearer(authorization)
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return sub


def require_supabase_uid_and_email(authorization: str | None = Header(default=None)) -> tuple[str, str]:
    """Returns (auth.users id, email) from Supabase JWT — for portal billing tied to signed-in user."""
    payload = _decode_supabase_bearer(authorization)
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="No email on access token")
    return (sub, email)
