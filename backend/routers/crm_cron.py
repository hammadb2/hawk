"""CRM scheduled jobs — aging reminders (WhatsApp stub), called by Vercel/Railway cron with secret header."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException

from config import CRM_PUBLIC_BASE_URL
from services.crm_monthly_reports import run_monthly_client_reports
from services.crm_portal_sequence_worker import process_due_onboarding_sequences
from services.crm_charlotte_run import run_charlotte_daily
from services.crm_shield_daily import run_daily_shield_rescans
from services.crm_twilio import format_stale_deal_message, send_whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/cron", tags=["crm-cron"])

# Prefer CRM-specific secret, then HAWK_CRON_SECRET, then CRON_SECRET (Railway).
CRON_SECRET = (
    os.environ.get("HAWK_CRM_CRON_SECRET", "").strip()
    or os.environ.get("HAWK_CRON_SECRET", "").strip()
    or os.environ.get("CRON_SECRET", "").strip()
)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _require_secret(x_cron_secret: str | None) -> None:
    if not CRON_SECRET:
        logger.warning("Cron secret not set (HAWK_CRM_CRON_SECRET / HAWK_CRON_SECRET / CRON_SECRET) — rejecting")
        raise HTTPException(status_code=503, detail="Cron not configured")
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/aging")
def aging_hourly(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    Hourly job: find prospects inactive ~10 days for WhatsApp (stub).
    Kanban borders refresh client-side every 60s; this endpoint is for rep nudges.
    """
    _require_secret(x_cron_secret)

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {
            "ok": True,
            "mode": "stub",
            "message": "Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to scan prospects for 10-day WhatsApp alerts.",
            "whatsapp_sent": 0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    cutoff_iso = cutoff.isoformat()
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    url = f"{SUPABASE_URL}/rest/v1/prospects"
    params = {
        "select": "id,domain,assigned_rep_id,last_activity_at,stage",
        "last_activity_at": f"lt.{cutoff_iso}",
    }
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=30.0)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        logger.exception("aging cron supabase fetch failed: %s", e)
        raise HTTPException(status_code=502, detail="Supabase fetch failed") from e

    candidates = [x for x in rows if x.get("stage") not in ("lost", "closed_won")]
    for row in candidates:
        logger.info("aging candidate prospect=%s rep=%s", row.get("id"), row.get("assigned_rep_id"))

    return {"ok": True, "mode": "live", "candidates": len(candidates), "whatsapp_sent": 0}


@router.post("/onboarding-drip")
def onboarding_drip(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Send due client onboarding / drip emails (Phase 2B)."""
    _require_secret(x_cron_secret)
    return process_due_onboarding_sequences()


@router.post("/stale-pipeline")
def stale_pipeline_whatsapp(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    Phase 2C — WhatsApp assigned rep when a prospect is in Call Booked or Proposal Sent
    with no activity for 48+ hours.
    """
    _require_secret(x_cron_secret)

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": True, "mode": "stub", "sent": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=headers,
        params={
            "select": "id,domain,company_name,stage,assigned_rep_id,last_activity_at",
            "last_activity_at": f"lt.{cutoff.isoformat()}",
            "limit": "200",
        },
        timeout=45.0,
    )
    r.raise_for_status()
    stale_stages = {"call_booked", "proposal_sent"}
    rows = [x for x in (r.json() or []) if x.get("stage") in stale_stages]
    base = CRM_PUBLIC_BASE_URL.rstrip("/")
    sent = 0
    for row in rows:
        rid = row.get("assigned_rep_id")
        if not rid:
            continue
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=headers,
            params={"id": f"eq.{rid}", "select": "full_name,email,whatsapp_number", "limit": "1"},
            timeout=20.0,
        )
        pr.raise_for_status()
        reps = pr.json()
        if not reps:
            continue
        rep = reps[0]
        wa = rep.get("whatsapp_number")
        if not wa:
            continue
        company = row.get("company_name") or row.get("domain") or "Prospect"
        domain = row.get("domain") or "—"
        pid = row["id"]
        msg = format_stale_deal_message(
            company=str(company),
            domain=str(domain),
            stage=str(row.get("stage") or ""),
            rep_name=str(rep.get("full_name") or rep.get("email") or "Rep"),
            prospect_url=f"{base}/crm/prospects/{pid}",
        )
        out = send_whatsapp(str(wa), msg)
        if not out.get("skipped"):
            sent += 1

    return {"ok": True, "candidates": len(rows), "whatsapp_sent": sent}


@router.post("/monthly-reports")
def monthly_reports_pdf(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    Phase 3C — first of month (schedule ~7am America/Denver): PDF per active portal client,
    upload to Storage `reports`, email via Resend, log to crm_monthly_report_log.
    """
    _require_secret(x_cron_secret)
    return run_monthly_client_reports()


@router.post("/charlotte-run")
def charlotte_daily_run(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    Charlotte automation — daily ~8am MST via cron-job.org:
    Apollo (200) → ZeroBounce → suppressions + CRM dedupe → Scanner (10 concurrent) → Claude → Smartlead → charlotte_runs + CEO WhatsApp.

    Header: X-Cron-Secret (same as other CRM crons: HAWK_CRM_CRON_SECRET / HAWK_CRON_SECRET / CRON_SECRET).
    Set CHARLOTTE_AUTOMATION_DRY_RUN=1 on the API to skip external calls (smoke test).
    """
    _require_secret(x_cron_secret)
    try:
        return run_charlotte_daily()
    except Exception as e:
        logger.exception("charlotte run failed: %s", e)
        try:
            send_whatsapp(
                os.environ.get("CRM_CEO_WHATSAPP_E164", "").strip() or "+18259458282",
                f"Charlotte run failed: {e!s}"[:1500],
            )
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/daily-shield-rescan")
def daily_shield_rescan(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    2A — Daily Shield client rescan (schedule ~6am America/Denver on Railway cron).
    Rescans each active Shield client domain, diffs finding fingerprints vs last snapshot,
    alerts only on NEW critical/high via WhatsApp (prospect phone) + email (portal profile).
    First run per client records baseline only (no alert).
    """
    _require_secret(x_cron_secret)
    try:
        return run_daily_shield_rescans()
    except Exception as e:
        logger.exception("daily shield rescan failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/weekly-threat-digest")
def weekly_threat_digest_stub(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """4B — Weekly AI threat briefing per industry. TODO: Claude + web search + Resend."""
    _require_secret(x_cron_secret)
    return {"ok": True, "phase": "4B", "implemented": False}


@router.post("/rep-health-score")
def rep_health_score_stub(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """4C — Daily rep health scoring. TODO: activity + pipeline metrics → profiles.health_score."""
    _require_secret(x_cron_secret)
    return {"ok": True, "phase": "4C", "implemented": False}


# scanner-health, va-reply-escalation, charlotte-quality-check live in routers/crm_scale.cron_routes (mounted in main.py).
