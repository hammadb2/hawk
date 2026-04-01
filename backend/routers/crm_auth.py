"""Shared Supabase JWT verification for CRM FastAPI routes."""

from __future__ import annotations

import logging
import os

from fastapi import Header, HTTPException
from jose import JWTError, jwt

from config import SUPABASE_JWT_SECRET

logger = logging.getLogger(__name__)


def require_supabase_uid(authorization: str | None = Header(default=None)) -> str:
    """Bearer access token from Supabase Auth (anon sign-in). Returns auth.users id."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=503, detail="SUPABASE_JWT_SECRET not configured on API")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError:
        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except JWTError as e:
            logger.warning("jwt decode failed: %s", e)
            raise HTTPException(status_code=401, detail="Invalid token") from e
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return sub
