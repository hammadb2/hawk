"""arq tasks — same process model as BullMQ workers (Redis broker)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.pipeline.runner import run_scan, run_scan_fast
from app.settings import get_settings

logger = logging.getLogger(__name__)

JOB_TIMEOUT_FAST_SEC = 120.0
JOB_TIMEOUT_FULL_SEC = 300.0


async def _log_scanner_failure(
    *,
    domain: str,
    error_message: str,
    scan_depth: str,
    layer: str | None = None,
) -> None:
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        return
    url = f"{s.supabase_url.rstrip('/')}/rest/v1/scanner_failures"
    headers = {
        "apikey": s.supabase_service_role_key,
        "Authorization": f"Bearer {s.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    body = {
        "domain": domain[:500],
        "error_message": error_message[:8000],
        "layer": (layer or "pipeline")[:200],
        "scan_depth": (scan_depth or "full")[:32],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=headers, json=body)
            if r.status_code >= 400:
                logger.warning("scanner_failures insert failed: %s %s", r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("scanner_failures insert exception: %s", e)


async def _maybe_supabase_insert(prospect_id: str | None, payload: dict[str, Any]) -> None:
    if not prospect_id:
        return
    if payload.get("score") is None and payload.get("message") == "scan_timeout":
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
        "attack_paths": payload.get("attack_paths") or [],
        "insurance_readiness": payload.get("insurance_readiness") or {},
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
    company_name: str | None = None,
    scan_depth: str = "full",
    trust_level: str = "public",
) -> dict[str, Any]:
    settings = get_settings()
    job_id = str(ctx.get("job_id", ""))
    depth = (scan_depth or "full").strip().lower()
    tl = (trust_level or "public").strip().lower()
    if tl not in ("public", "subscriber", "certified"):
        tl = "public"

    async def _execute():
        if depth == "fast":
            return await run_scan_fast(
                domain,
                scan_id=scan_id,
                industry=industry,
                company_name=company_name,
                settings=settings,
                trust_level=tl,
            )
        return await run_scan(
            domain,
            scan_id=scan_id,
            industry=industry,
            company_name=company_name,
            settings=settings,
            trust_level=tl,
        )

    budget = JOB_TIMEOUT_FAST_SEC if depth == "fast" else JOB_TIMEOUT_FULL_SEC
    for attempt in range(2):
        try:
            result = await asyncio.wait_for(_execute(), timeout=budget)
            out = result.model_dump(mode="json")
            out["ok"] = True
            out["job_id"] = job_id
            await _maybe_supabase_insert(prospect_id, {**out, "job_id": job_id})
            return out
        except asyncio.TimeoutError:
            timeout_payload: dict[str, Any] = {
                "domain": domain.strip().lower(),
                "status": "timed_out",
                "score": None,
                "grade": None,
                "findings": [],
                "message": "scan_timeout",
                "scan_version": "2.0-fast" if depth == "fast" else "2.0",
                "ok": False,
                "job_id": job_id,
            }
            await _maybe_supabase_insert(prospect_id, {**timeout_payload, "job_id": job_id})
            return timeout_payload
        except Exception as e:
            logger.warning("scan attempt %s failed: %s", attempt + 1, e)
            if attempt == 0:
                continue
            await _log_scanner_failure(domain=domain, error_message=str(e), scan_depth=depth)
            raise
