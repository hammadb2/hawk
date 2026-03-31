"""arq tasks — same process model as BullMQ workers (Redis broker)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.pipeline.runner import run_scan
from app.settings import get_settings

logger = logging.getLogger(__name__)


async def _maybe_supabase_insert(prospect_id: str | None, payload: dict[str, Any]) -> None:
    if not prospect_id:
        return
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        return
    url = f"{s.supabase_url.rstrip('/')}/rest/v1/crm_prospect_scans"
    headers = {
        "apikey": s.supabase_service_role_key,
        "Authorization": f"Bearer {s.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    body = {
        "prospect_id": prospect_id,
        "hawk_score": payload.get("score"),
        "grade": payload.get("grade"),
        "findings": {
            "source": "hawk_scanner_v2",
            "findings": payload.get("findings"),
            "raw_layers_keys": list((payload.get("raw_layers") or {}).keys()),
        },
        "status": "complete",
        "scan_version": payload.get("scan_version", "2.0"),
        "industry": payload.get("industry"),
        "raw_layers": payload.get("raw_layers"),
        "interpreted_findings": payload.get("interpreted_findings"),
        "breach_cost_estimate": payload.get("breach_cost_estimate"),
        "external_job_id": payload.get("job_id"),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code >= 400:
            logger.warning("Supabase insert failed: %s %s", r.status_code, r.text[:500])


async def run_scan_task(
    ctx: dict[str, Any],
    domain: str,
    industry: str | None = None,
    prospect_id: str | None = None,
    scan_id: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    job_id = str(ctx.get("job_id", ""))
    try:
        result = await run_scan(domain, scan_id=scan_id, industry=industry, settings=settings)
    except Exception as e:
        logger.exception("scan failed: %s", e)
        raise

    out = result.model_dump(mode="json")
    out["ok"] = True
    out["job_id"] = job_id
    await _maybe_supabase_insert(prospect_id, {**out, "job_id": job_id})
    return out
