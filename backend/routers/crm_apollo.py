"""
CRM Apollo enrichment — optional. Without APOLLO_API_KEY the endpoint returns configured=false.
With a key set, performs a minimal org search and merges into prospect.apollo_data (service role).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.services.supabase_crm import get_supabase, supabase_available, update_prospect

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/apollo", tags=["crm-apollo"])


class EnrichBody(BaseModel):
    domain: str


def _actor_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    if not token or not supabase_available():
        return None
    try:
        sb = get_supabase()
        res = sb.auth.get_user(token)
        return res.user.id if res.user else None
    except Exception:
        return None


@router.post("/enrich")
async def apollo_enrich(request: Request, body: EnrichBody) -> dict[str, Any]:
    actor_id = _actor_from_request(request)
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    domain = (body.domain or "").strip().lower().lstrip("@")
    if not domain or "." not in domain:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Valid domain required")

    api_key = os.environ.get("APOLLO_API_KEY") or os.environ.get("APOLLO_IO_API_KEY") or ""
    if not api_key:
        return {
            "configured": False,
            "message": "Set APOLLO_API_KEY (or APOLLO_IO_API_KEY) on the API server for live enrichment.",
        }

    if not supabase_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")

    try:
        sb = get_supabase()
        pres = sb.table("prospects").select("id, apollo_data").eq("domain", domain).limit(1).execute()
        if not pres.data:
            return {"configured": True, "matched": False, "message": f"No prospect found for domain {domain}"}

        prospect_id = pres.data[0]["id"]
        existing = pres.data[0].get("apollo_data") or {}

        # Apollo Organization Search (minimal)
        url = "https://api.apollo.io/api/v1/organizations/search"
        headers = {"Content-Type": "application/json", "Cache-Control": "no-cache"}
        payload = {"api_key": api_key, "q_organization_domains": domain, "page": 1, "per_page": 1}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            logger.warning("Apollo API error %s: %s", resp.status_code, resp.text[:500])
            return {
                "configured": True,
                "matched": True,
                "message": f"Apollo returned HTTP {resp.status_code}",
                "prospect_id": prospect_id,
            }

        data = resp.json()
        orgs = data.get("organizations") or []
        org = orgs[0] if orgs else None
        merged = {
            **existing,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "source": "apollo",
            "organization": org,
        }

        update_prospect(prospect_id, {"apollo_data": merged})

        return {
            "configured": True,
            "matched": True,
            "prospect_id": prospect_id,
            "organization_name": (org or {}).get("name"),
        }
    except httpx.RequestError as exc:
        logger.error("Apollo request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Apollo API",
        ) from exc
    except Exception as exc:
        logger.error("apollo_enrich error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Enrichment failed",
        ) from exc
