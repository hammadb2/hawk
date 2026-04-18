"""ARIA — Outbound Pipeline API endpoints.

Provides endpoints to trigger, monitor, pause/resume, and download reports
for the ARIA autonomous outbound pipeline.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import SUPABASE_URL
from routers.crm_auth import require_supabase_uid
from services.aria_pipeline import (
    pause_pipeline,
    resume_pipeline,
    run_outbound_pipeline,
    _build_summary,
    _get_run,
    _get_run_leads,
)
from services.aria_pipeline_report import (
    generate_pipeline_report_pdf,
    upload_report_to_storage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/aria", tags=["aria-pipeline"])

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# ── Access Control ────────────────────────────────────────────────────────

PIPELINE_ALLOWED_ROLES = {"ceo"}
PIPELINE_ALLOWED_ROLE_TYPES = {"ceo", "va_manager"}


def _get_profile(uid: str) -> dict[str, Any] | None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _require_pipeline_access(uid: str) -> dict[str, Any]:
    """Ensure user has access to ARIA pipeline. Returns profile."""
    prof = _get_profile(uid)
    if not prof:
        raise HTTPException(status_code=403, detail="Profile not found")
    role = prof.get("role", "")
    role_type = prof.get("role_type", "")
    if role not in PIPELINE_ALLOWED_ROLES and role_type not in PIPELINE_ALLOWED_ROLE_TYPES:
        raise HTTPException(status_code=403, detail="ARIA pipeline access denied for your role")
    return prof


# ── Request/Response Models ───────────────────────────────────────────────

class RunPipelineRequest(BaseModel):
    vertical: str  # "dental", "legal", "accounting"
    location: str  # e.g. "Canada", "Ontario, Canada"
    batch_size: int = 50


class SchedulePipelineRequest(BaseModel):
    vertical: str
    location: str
    batch_size: int = 50
    scheduled_for: str  # ISO timestamp
    recurring: bool = False
    recurring_cron: str | None = None  # e.g. "0 7 * * *" for daily 7am


# ── Pipeline Run Endpoints ────────────────────────────────────────────────

@router.post("/pipeline/run")
def trigger_pipeline(
    body: RunPipelineRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(require_supabase_uid),
):
    """Trigger a full ARIA outbound pipeline run. Returns immediately with the run ID;
    the pipeline executes in the background."""
    prof = _require_pipeline_access(uid)

    if body.vertical not in ("dental", "legal", "accounting"):
        raise HTTPException(status_code=400, detail="Invalid vertical. Must be dental, legal, or accounting.")
    if not body.location.strip():
        raise HTTPException(status_code=400, detail="Location is required.")
    if body.batch_size < 1 or body.batch_size > 500:
        raise HTTPException(status_code=400, detail="Batch size must be between 1 and 500.")

    # Create pipeline run record
    run_payload = {
        "triggered_by": uid,
        "vertical": body.vertical,
        "location": body.location.strip(),
        "batch_size": body.batch_size,
        "status": "running",
        "current_step": "apify_discover",
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
        headers=_sb_headers(),
        json=run_payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=500, detail=f"Failed to create pipeline run: {r.text[:300]}")

    run_data = r.json()
    run_id = run_data[0]["id"] if isinstance(run_data, list) and run_data else run_data.get("id", "")

    if not run_id:
        raise HTTPException(status_code=500, detail="Failed to get run ID")

    # Log the action
    _log_action(uid, "run_outbound_pipeline", {
        "vertical": body.vertical,
        "location": body.location,
        "batch_size": body.batch_size,
        "run_id": run_id,
    })

    # Execute pipeline in background thread (not asyncio background task,
    # since the pipeline uses asyncio.run() internally for scan/email batches)
    def _run_in_thread() -> None:
        try:
            run_outbound_pipeline(run_id, body.vertical, body.location.strip(), body.batch_size)
        except Exception as exc:
            logger.exception("Background pipeline run failed: %s", exc)

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()

    return {
        "run_id": run_id,
        "status": "running",
        "message": f"ARIA pipeline started for {body.vertical} in {body.location}. Batch size: {body.batch_size}.",
    }


@router.get("/pipeline/{run_id}/status")
def get_pipeline_status(
    run_id: str,
    uid: str = Depends(require_supabase_uid),
):
    """Get live status of a pipeline run."""
    _require_pipeline_access(uid)
    summary = _build_summary(run_id)
    if "error" in summary and summary.get("error") == "Run not found":
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return summary


@router.get("/pipeline/{run_id}/leads")
def get_pipeline_leads(
    run_id: str,
    uid: str = Depends(require_supabase_uid),
):
    """Get all leads for a pipeline run."""
    _require_pipeline_access(uid)
    run = _get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    leads = _get_run_leads(run_id)
    return {"run_id": run_id, "leads": leads, "total": len(leads)}


@router.get("/pipeline/{run_id}/report")
def get_pipeline_report(
    run_id: str,
    uid: str = Depends(require_supabase_uid),
):
    """Generate and return a downloadable PDF report for a pipeline run."""
    _require_pipeline_access(uid)
    run = _get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    pdf_bytes = generate_pipeline_report_pdf(run_id)
    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="Failed to generate report PDF")

    # Upload to storage and get signed URL
    signed_url = upload_report_to_storage(run_id, pdf_bytes)

    if signed_url:
        return {
            "run_id": run_id,
            "download_url": signed_url,
            "filename": f"aria-pipeline-{run.get('vertical', 'report')}-{run_id[:8]}.pdf",
        }

    # Fallback: return report data as JSON if storage upload fails
    return {
        "run_id": run_id,
        "download_url": None,
        "error": "Storage upload failed — report generated but could not be stored",
        "summary": _build_summary(run_id),
    }


@router.post("/pipeline/{run_id}/pause")
def pause_pipeline_run(
    run_id: str,
    uid: str = Depends(require_supabase_uid),
):
    """Pause a running pipeline."""
    _require_pipeline_access(uid)
    result = pause_pipeline(run_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    _log_action(uid, "pause_pipeline", {"run_id": run_id})
    return result


@router.post("/pipeline/{run_id}/resume")
def resume_pipeline_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    uid: str = Depends(require_supabase_uid),
):
    """Resume a paused pipeline."""
    prof = _require_pipeline_access(uid)
    run = _get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    if run.get("status") != "paused":
        raise HTTPException(status_code=400, detail=f"Cannot resume — run status is {run.get('status')}")

    _log_action(uid, "resume_pipeline", {"run_id": run_id})

    # Resume in background thread
    def _resume_in_thread() -> None:
        try:
            resume_pipeline(run_id, uid)
        except Exception as exc:
            logger.exception("Background pipeline resume failed: %s", exc)

    thread = threading.Thread(target=_resume_in_thread, daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "running", "message": "Pipeline resumed."}


@router.get("/pipeline/runs")
def list_pipeline_runs(
    uid: str = Depends(require_supabase_uid),
    limit: int = 20,
):
    """List pipeline runs for the authenticated user."""
    _require_pipeline_access(uid)

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
        headers=_sb_headers(),
        params={
            "select": "id,vertical,location,status,current_step,leads_pulled,emails_sent,vulnerabilities_found,started_at,completed_at",
            "order": "created_at.desc",
            "limit": str(min(limit, 100)),
        },
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=500, detail="Failed to fetch pipeline runs")
    return {"runs": r.json() or []}


# ── Scheduled Pipeline Runs ──────────────────────────────────────────────

@router.post("/pipeline/schedule")
def schedule_pipeline(
    body: SchedulePipelineRequest,
    uid: str = Depends(require_supabase_uid),
):
    """Schedule a pipeline run for a future time."""
    _require_pipeline_access(uid)

    if body.vertical not in ("dental", "legal", "accounting"):
        raise HTTPException(status_code=400, detail="Invalid vertical.")

    payload = {
        "triggered_by": uid,
        "action_type": "run_outbound_pipeline",
        "action_payload": {
            "vertical": body.vertical,
            "location": body.location.strip(),
            "batch_size": body.batch_size,
            "recurring": body.recurring,
            "recurring_cron": body.recurring_cron,
        },
        "scheduled_for": body.scheduled_for,
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_scheduled_actions",
        headers=_sb_headers(),
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=500, detail=f"Failed to schedule pipeline: {r.text[:300]}")

    sched_data = r.json()
    sched_id = sched_data[0]["id"] if isinstance(sched_data, list) and sched_data else sched_data.get("id", "")

    _log_action(uid, "schedule_pipeline", {
        "vertical": body.vertical,
        "location": body.location,
        "scheduled_for": body.scheduled_for,
        "schedule_id": sched_id,
    })

    return {
        "scheduled": True,
        "schedule_id": sched_id,
        "scheduled_for": body.scheduled_for,
        "message": f"Pipeline for {body.vertical} in {body.location} scheduled for {body.scheduled_for}.",
    }


# ── Action Logging ────────────────────────────────────────────────────────

def _log_action(uid: str, action_type: str, payload: dict[str, Any], result: str = "triggered") -> None:
    """Log ARIA action to aria_action_log."""
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_action_log",
            headers=_sb_headers(),
            json={
                "triggered_by": uid,
                "action_type": action_type,
                "action_payload": payload,
                "action_result": result,
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.exception("Failed to log ARIA action: %s", exc)
