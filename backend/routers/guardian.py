"""Guardian browser extension API — profile fetch + threat event ingestion (shared secret)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from config import SUPABASE_URL
from services.guardian_client_alerts import on_guardian_threat_event
from services.guardian_client_profiler import build_client_guardian_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guardian", tags=["guardian"])

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _require_extension_secret(x_guardian_extension_secret: str | None) -> None:
    expected = os.environ.get("GUARDIAN_EXTENSION_SECRET", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="GUARDIAN_EXTENSION_SECRET not configured on API")
    got = (x_guardian_extension_secret or "").strip()
    if got != expected:
        raise HTTPException(status_code=401, detail="Invalid Guardian extension secret")


def _service_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


class GuardianLogEventBody(BaseModel):
    client_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    severity: str = Field(default="medium")
    details: dict[str, Any] = Field(default_factory=dict)
    page_url: str | None = None
    source: str = Field(default="extension")


@router.get("/client-profile/{client_id}")
def get_client_guardian_profile(
    client_id: str,
    x_guardian_extension_secret: str | None = Header(None, alias="X-Guardian-Extension-Secret"),
) -> dict[str, Any]:
    _require_extension_secret(x_guardian_extension_secret)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    cid = client_id.strip()
    h = _service_headers()
    gr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_guardian_profiles",
        headers=h,
        params={"client_id": f"eq.{cid}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    gr.raise_for_status()
    rows = gr.json() or []
    if not rows:
        built = build_client_guardian_profile(cid)
        if not built.get("ok"):
            raise HTTPException(status_code=502, detail=built.get("error") or "profiler failed")
        gr2 = httpx.get(
            f"{SUPABASE_URL}/rest/v1/client_guardian_profiles",
            headers=h,
            params={"client_id": f"eq.{cid}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        gr2.raise_for_status()
        rows = gr2.json() or []
        if not rows:
            raise HTTPException(status_code=404, detail="profile not found after build")
    return {"ok": True, "profile": rows[0]}


@router.post("/log-event")
def log_guardian_event(
    body: GuardianLogEventBody,
    x_guardian_extension_secret: str | None = Header(None, alias="X-Guardian-Extension-Secret"),
) -> dict[str, Any]:
    _require_extension_secret(x_guardian_extension_secret)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    src = body.source.strip().lower() if body.source else "extension"
    if src not in ("extension", "api"):
        src = "extension"

    allowed_sev = ("info", "low", "medium", "high", "critical")
    sev = (body.severity or "medium").lower().strip()
    if sev not in allowed_sev:
        sev = "medium"

    row = {
        "client_id": body.client_id.strip(),
        "event_type": body.event_type.strip()[:200],
        "severity": sev,
        "details": body.details or {},
        "source": src,
        "page_url": (body.page_url or "")[:2000] or None,
    }
    h = _service_headers()
    ins = httpx.post(
        f"{SUPABASE_URL}/rest/v1/guardian_events",
        headers={**h, "Prefer": "return=representation"},
        json=row,
        timeout=20.0,
    )
    if ins.status_code >= 400:
        logger.warning("guardian_events insert failed: %s %s", ins.status_code, ins.text[:400])
        raise HTTPException(status_code=502, detail=ins.text[:500])

    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=h,
        params={"id": f"eq.{row['client_id']}", "select": "company_name", "limit": "1"},
        timeout=15.0,
    )
    company = None
    if cr.status_code < 400 and cr.json():
        company = cr.json()[0].get("company_name")

    try:
        on_guardian_threat_event(
            client_id=row["client_id"],
            event_type=row["event_type"],
            severity=row["severity"],
            details={**(body.details or {}), "page_url": body.page_url},
            company_name=company,
        )
    except Exception:
        logger.exception("guardian alerts pipeline failed client_id=%s", row["client_id"])

    out = ins.json()
    saved = out[0] if isinstance(out, list) and out else out
    return {"ok": True, "event": saved}
