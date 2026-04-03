"""Phase 4 — CRM: monitored enterprise domains (max 4 extras)."""

from __future__ import annotations

import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid
from services.crm_client_portal_provision import assert_crm_staff_can_provision

router = APIRouter(tags=["crm-enterprise"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", re.I)


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _normalize_domains(raw: list[str]) -> list[str]:
    out: list[str] = []
    for x in raw:
        d = str(x).strip().lower().rstrip(".")
        if not d:
            continue
        if d.startswith("http://"):
            d = d[7:].split("/")[0]
        elif d.startswith("https://"):
            d = d[8:].split("/")[0]
        if d.startswith("www."):
            d = d[4:]
        if not _DOMAIN_RE.match(d):
            raise HTTPException(status_code=400, detail=f"Invalid domain: {x!r}")
        if d not in out:
            out.append(d)
        if len(out) > 4:
            raise HTTPException(status_code=400, detail="At most 4 additional monitored domains")
    return out


class MonitoredDomainsBody(BaseModel):
    domains: list[str] = Field(default_factory=list, max_length=4)


@router.patch("/api/crm/clients/{client_id}/monitored-domains")
def patch_monitored_domains(
    client_id: str,
    body: MonitoredDomainsBody,
    uid: str = Depends(require_supabase_uid),
):
    assert_crm_staff_can_provision(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    normalized = _normalize_domains(body.domains)

    gr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={"id": f"eq.{client_id}", "select": "id,domain", "limit": "1"},
        timeout=20.0,
    )
    gr.raise_for_status()
    crow = (gr.json() or [None])[0]
    if not crow:
        raise HTTPException(status_code=404, detail="Client not found")
    primary = str((crow.get("domain") or "")).strip().lower().rstrip(".")
    if primary:
        primary = primary.replace("www.", "", 1)
        normalized = [d for d in normalized if d != primary]

    patch = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={"id": f"eq.{client_id}"},
        json={"monitored_domains": normalized},
        timeout=20.0,
    )
    if patch.status_code >= 400:
        raise HTTPException(status_code=502, detail=patch.text[:400])

    return {"ok": True, "client_id": client_id, "monitored_domains": normalized}
