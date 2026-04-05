"""HAWK Scanner 2.0 — FastAPI + Redis (arq) queue. Deploy on Railway beside Redis."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import asyncio

from app.models import ScanRequest, ScanResponse
from app.pipeline.runner import run_dnstwist_only, run_scan, run_scan_fast
from app.settings import get_settings

logger = logging.getLogger(__name__)

redis_pool: ArqRedis | None = None

SCAN_JOB_TIMEOUT_FAST_SEC = 120.0
SCAN_JOB_TIMEOUT_FULL_SEC = 300.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_pool
    s = get_settings()
    try:
        redis_pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
    except Exception as e:
        logger.warning("Redis pool not initialized (async scans disabled): %s", e)
        redis_pool = None
    yield
    if redis_pool:
        await redis_pool.close()
        redis_pool = None


app = FastAPI(
    title="HAWK Scanner 2.0",
    description="Attack-surface pipeline: subfinder, naabu, httpx, whatweb, NVD supply-chain, nuclei, dnstwist, HIBP, GitHub, Claude.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "hawk-scanner-v2"}


@app.post("/scan", response_model=None)
async def scan_specter_compat(req: ScanRequest) -> dict[str, Any]:
    """Drop-in compatible with Specter `POST /scan` (used by HAWK API relay)."""
    return await _sync_scan_body(req)


@app.post("/v1/scan/dnstwist", response_model=None)
async def scan_dnstwist_only(req: ScanRequest) -> dict[str, Any]:
    """Registered-domain / lookalike pass only — for daily Shield typosquat monitoring."""
    try:
        result = await asyncio.wait_for(
            run_dnstwist_only(
                req.domain,
                scan_id=req.scan_id,
                industry=req.industry,
                company_name=req.company_name,
            ),
            timeout=180.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="dnstwist_timeout") from None
    return result.model_dump(mode="json")


class AsyncScanBody(BaseModel):
    domain: str = Field(..., min_length=1)
    industry: str | None = None
    company_name: str | None = None
    prospect_id: str | None = Field(None, description="If set + Supabase env, worker inserts crm_prospect_scans")
    scan_id: str | None = None
    scan_depth: str = Field(default="full", description="full | fast")


@app.post("/v1/scan/async")
async def enqueue_scan(body: AsyncScanBody) -> dict[str, str]:
    if not redis_pool:
        raise HTTPException(status_code=503, detail="Redis not configured; async queue unavailable.")
    job = await redis_pool.enqueue_job(
        "run_scan_task",
        body.domain,
        body.industry,
        body.prospect_id,
        body.scan_id,
        body.company_name,
        body.scan_depth or "full",
    )
    if job is None:
        raise HTTPException(status_code=409, detail="Job id conflict or duplicate enqueue")
    return {"job_id": job.job_id, "status": "queued"}


@app.get("/v1/jobs/{job_id}")
async def job_result(job_id: str) -> dict[str, Any]:
    if not redis_pool:
        raise HTTPException(status_code=503, detail="Redis not configured.")
    job = Job(job_id, redis_pool)
    status = await job.status()
    if status == JobStatus.not_found:
        raise HTTPException(status_code=404, detail="Job not found")
    if status != JobStatus.complete:
        return {"job_id": job_id, "status": status.value}
    info = await job.result_info()
    if info is None:
        return {"job_id": job_id, "status": status.value}
    if not info.success:
        return {"job_id": job_id, "status": "failed", "error": str(info.result)}
    return {"job_id": job_id, "status": "complete", "result": info.result}


async def _sync_scan_body(req: ScanRequest) -> dict[str, Any]:
    depth = (req.scan_depth or "full").strip().lower()
    budget = SCAN_JOB_TIMEOUT_FAST_SEC if depth == "fast" else SCAN_JOB_TIMEOUT_FULL_SEC
    if depth == "fast":
        coro = run_scan_fast(
            req.domain,
            scan_id=req.scan_id,
            industry=req.industry,
            company_name=req.company_name,
        )
    else:
        coro = run_scan(
            req.domain,
            scan_id=req.scan_id,
            industry=req.industry,
            company_name=req.company_name,
        )
    try:
        result = await asyncio.wait_for(coro, timeout=budget)
    except asyncio.TimeoutError:
        return {
            "domain": req.domain.strip().lower(),
            "status": "timed_out",
            "score": None,
            "grade": None,
            "findings": [],
            "message": "scan_timeout",
            "scan_version": "2.0" if depth != "fast" else "2.0-fast",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}") from e
    return result.model_dump(mode="json")


@app.post("/v1/scan/sync", response_model=None)
async def sync_scan(req: ScanRequest) -> dict[str, Any]:
    """Synchronous scan: fast (~15s target) or full pipeline. Hard timeout 120s with minimal payload on timeout."""
    return await _sync_scan_body(req)
