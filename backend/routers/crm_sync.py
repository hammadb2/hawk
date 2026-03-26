"""
CRM Sync Router
Endpoints for triggering HAWK product → CRM data sync.

Routes:
  POST /api/crm/sync/event          — event-driven single-account sync (from HAWK product)
  POST /api/crm/sync/account/{id}   — manual single-account sync (HoS/CEO)
  POST /api/crm/sync/all            — trigger full background sync (cron / admin)
  GET  /api/crm/sync/status         — last sync timestamps

The 6-hour background job is registered on app startup via APScheduler.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from backend.services.supabase_crm import supabase_available, get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/sync", tags=["crm-sync"])

SYNC_SECRET = os.getenv("CRM_SYNC_SECRET", "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Models ───────────────────────────────────────────────────────────────────

class SyncEventPayload(BaseModel):
    """
    Sent by the HAWK product on key events (signup, plan change, cancellation intent, etc.)
    Provides event-specific context alongside the user ID.
    """
    hawk_user_id: str
    event: str                                 # signup, plan_change, cancellation_intent, payment_failed, login, nps_submitted, feature_accessed
    client_id: Optional[str] = None           # if known — omit for new signups
    plan: Optional[str] = None
    nps_score: Optional[int] = None
    nps_comment: Optional[str] = None
    payment_failed_count: Optional[int] = None
    feature: Optional[str] = None
    metadata: Optional[dict] = None
    secret: str = ""                           # shared secret for webhook auth


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _verify_secret(secret: str) -> None:
    if SYNC_SECRET and secret != SYNC_SECRET:
        raise HTTPException(status_code=401, detail="Invalid sync secret")


def _find_client_for_hawk_user(hawk_user_id: str) -> Optional[dict]:
    try:
        sb = get_supabase()
        res = (
            sb.table("clients")
            .select("id, closing_rep_id, csm_rep_id, company_name")
            .eq("hawk_user_id", hawk_user_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as exc:
        logger.error("_find_client_for_hawk_user error: %s", exc)
        return None


def _run_single_sync(hawk_user_id: str, client_id: str, **kwargs) -> None:
    """Background task: sync one account."""
    try:
        from backend.services.product_bridge import sync_account
        sync_account(hawk_user_id, client_id, **kwargs)
    except Exception as exc:
        logger.error("Background sync failed for hawk_user %s: %s", hawk_user_id, exc)


def _run_full_sync() -> None:
    """Background task: sync all active clients that have a hawk_user_id."""
    if not supabase_available():
        return
    try:
        sb = get_supabase()
        clients_res = (
            sb.table("clients")
            .select("id, hawk_user_id")
            .eq("status", "active")
            .not_.is_("hawk_user_id", "null")
            .execute()
        )
        clients = clients_res.data or []
        logger.info("Full sync: processing %d active clients", len(clients))

        from backend.services.product_bridge import sync_account
        for client in clients:
            try:
                sync_account(client["hawk_user_id"], client["id"])
            except Exception as exc:
                logger.error("Full sync: client %s failed: %s", client["id"], exc)

    except Exception as exc:
        logger.error("Full sync failed: %s", exc)


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/event")
async def sync_event(payload: SyncEventPayload, background_tasks: BackgroundTasks):
    """
    Event-driven sync — called by the HAWK product on key events.
    Immediately updates the relevant field, then queues a full account sync.
    """
    _verify_secret(payload.secret)

    if not supabase_available():
        logger.warning("sync_event: Supabase not configured")
        return {"status": "skipped"}

    sb = get_supabase()
    hawk_user_id = payload.hawk_user_id

    # If client_id not provided, look it up by hawk_user_id
    client_id = payload.client_id
    if not client_id:
        client = _find_client_for_hawk_user(hawk_user_id)
        if client:
            client_id = client["id"]

    # ── Handle event-specific immediate actions ──────────────────────
    event = payload.event

    if event == "cancellation_intent":
        logger.warning("Cancellation intent detected for HAWK user %s", hawk_user_id)
        if client_id:
            sb.table("clients").update({
                "churn_risk_score": "critical",
            }).eq("id", client_id).execute()

            from backend.services.supabase_crm import log_activity
            log_activity({
                "client_id": client_id,
                "type": "note_added",
                "notes": "🚨 Cancellation intent detected from HAWK product dashboard.",
                "metadata": {"urgent": True, "type": "cancellation_intent"},
            })

    elif event == "nps_submitted" and payload.nps_score is not None:
        if client_id:
            sb.table("clients").update({
                "nps_latest": payload.nps_score,
                "nps_comment": payload.nps_comment,
                "nps_at": _now(),
            }).eq("id", client_id).execute()

    elif event == "plan_change" and payload.plan:
        if client_id:
            from backend.services.supabase_crm import log_activity
            log_activity({
                "client_id": client_id,
                "type": "note_added",
                "notes": f"Plan changed to {payload.plan} in HAWK product.",
                "metadata": {"plan": payload.plan, "source": "product_event"},
            })

    elif event == "login":
        # Lightweight — just refresh the last_login_date in sync record
        if client_id:
            sb.table("client_health_sync").update({
                "last_login_date": _now(),
                "synced_at": _now(),
            }).eq("client_id", client_id).execute()

    elif event == "feature_accessed" and payload.feature and client_id:
        sb.table("client_health_sync").update({
            f"features_accessed->{payload.feature}": True,
            "synced_at": _now(),
        }).eq("client_id", client_id).execute()

    # ── Queue full account sync in background ────────────────────────
    if client_id:
        kwargs: dict = {}
        if payload.payment_failed_count is not None:
            kwargs["payment_failed_count"] = payload.payment_failed_count
        if event == "cancellation_intent":
            kwargs["cancellation_intent"] = True
        if payload.nps_score is not None:
            kwargs["nps_score"] = payload.nps_score
            kwargs["nps_comment"] = payload.nps_comment

        background_tasks.add_task(_run_single_sync, hawk_user_id, client_id, **kwargs)

    return {"status": "queued", "event": event, "hawk_user_id": hawk_user_id}


@router.post("/account/{client_id}")
async def sync_account_endpoint(client_id: str, background_tasks: BackgroundTasks):
    """Manual sync for a single client — triggered from the CRM client detail page."""
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()
    client_res = (
        sb.table("clients")
        .select("id, hawk_user_id")
        .eq("id", client_id)
        .single()
        .execute()
    )
    if not client_res.data:
        raise HTTPException(status_code=404, detail="Client not found")

    hawk_user_id = client_res.data.get("hawk_user_id")
    if not hawk_user_id:
        raise HTTPException(
            status_code=422,
            detail="Client has no linked HAWK account (hawk_user_id not set)",
        )

    background_tasks.add_task(_run_single_sync, hawk_user_id, client_id)
    return {"status": "queued", "client_id": client_id, "hawk_user_id": hawk_user_id}


@router.post("/all")
async def sync_all(background_tasks: BackgroundTasks, secret: str = ""):
    """Trigger full sync of all active clients. Protected by CRM_SYNC_SECRET."""
    _verify_secret(secret)
    background_tasks.add_task(_run_full_sync)
    return {"status": "queued", "triggered_at": _now()}


@router.get("/status")
async def sync_status():
    """Return last sync timestamps for all active clients."""
    if not supabase_available():
        return {"synced": []}

    try:
        sb = get_supabase()
        res = (
            sb.table("client_health_sync")
            .select("client_id, hawk_user_id, synced_at, churn_risk_label, churn_risk_numeric")
            .order("synced_at", desc=True)
            .limit(100)
            .execute()
        )
        return {"synced": res.data or []}
    except Exception as exc:
        logger.error("sync_status error: %s", exc)
        return {"synced": []}


# ─── APScheduler registration ─────────────────────────────────────────────────

def register_sync_scheduler(app) -> None:
    """
    Register the 6-hour background sync job on app startup.
    Call this from main.py:
        from backend.routers.crm_sync import register_sync_scheduler
        register_sync_scheduler(app)
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _run_full_sync,
            trigger=IntervalTrigger(hours=6),
            id="crm_full_sync",
            replace_existing=True,
            misfire_grace_time=300,
        )

        @app.on_event("startup")
        async def start_scheduler():
            scheduler.start()
            logger.info("CRM sync scheduler started — runs every 6 hours")

        @app.on_event("shutdown")
        async def stop_scheduler():
            scheduler.shutdown(wait=False)

    except ImportError:
        logger.warning(
            "apscheduler not installed — 6-hour sync job disabled. "
            "Install: pip install apscheduler>=3.10.0"
        )
