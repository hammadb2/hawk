"""CRM scheduled jobs — aging reminders, onboarding, Shield, Charlotte, Phase 4 crons (Vercel/Railway + X-Cron-Secret)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException

from config import CRM_PUBLIC_BASE_URL
from services.crm_monthly_reports import run_monthly_client_reports
from services.crm_portal_sequence_worker import process_due_onboarding_sequences
from services.crm_shield_daily import run_daily_shield_rescans
from services.crm_openphone import format_aging_deal_message, format_stale_deal_message, send_ceo_sms, send_sms
from routers.portal_phase2 import run_weekly_threat_briefings_for_all_clients
from services.crm_dnstwist_daily import run_daily_dnstwist_monitoring
from services.crm_rep_health import run_rep_health_scores
from services.crm_enterprise_domain_scans import run_enterprise_domain_scans
from services.crm_attacker_simulation import run_weekly_attacker_simulations
from services.portal_milestones import ensure_portal_milestones
from services.aria_memory import run_memory_ingestion
from services.aria_client_health import run_client_health_scores
from services.aria_briefing import run_monday_briefing, run_competitive_brief

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
    Hourly (or daily) job: prospects with no activity for 10+ days — WhatsApp nudge to assigned rep when
    `whatsapp_number` on profile is used as SMS destination (same pattern as stale-pipeline).
    """
    _require_secret(x_cron_secret)

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {
            "ok": True,
            "mode": "stub",
            "message": "Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to scan prospects for 10-day WhatsApp alerts.",
            "sms_sent": 0,
        }

    inactive_days = 10
    cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)
    cutoff_iso = cutoff.isoformat()
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    url = f"{SUPABASE_URL}/rest/v1/prospects"
    params = {
        "select": "id,domain,company_name,assigned_rep_id,last_activity_at,stage,last_aging_nudge_at",
        "last_activity_at": f"lt.{cutoff_iso}",
        "limit": "200",
    }
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=30.0)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        logger.exception("aging cron supabase fetch failed: %s", e)
        raise HTTPException(status_code=502, detail="Supabase fetch failed") from e

    candidates = [x for x in rows if x.get("stage") not in ("lost", "closed_won")]
    base = CRM_PUBLIC_BASE_URL.rstrip("/")
    now = datetime.now(timezone.utc)
    nudge_cooldown_sec = 48 * 3600
    sent = 0
    for row in candidates:
        logger.info("aging candidate prospect=%s rep=%s", row.get("id"), row.get("assigned_rep_id"))
        raw_nudge = row.get("last_aging_nudge_at")
        if raw_nudge:
            try:
                ln = datetime.fromisoformat(str(raw_nudge).replace("Z", "+00:00"))
                if ln.tzinfo is None:
                    ln = ln.replace(tzinfo=timezone.utc)
                if (now - ln).total_seconds() < nudge_cooldown_sec:
                    continue
            except Exception:
                pass
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
        msg = format_aging_deal_message(
            company=str(company),
            domain=str(domain),
            stage=str(row.get("stage") or ""),
            rep_name=str(rep.get("full_name") or rep.get("email") or "Rep"),
            prospect_url=f"{base}/crm/prospects/{pid}",
            days_inactive=inactive_days,
        )
        out = send_sms(str(wa), msg)
        if not out.get("skipped"):
            sent += 1
            pid = row["id"]
            try:
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/prospects",
                    headers=headers,
                    params={"id": f"eq.{pid}"},
                    json={"last_aging_nudge_at": now.isoformat()},
                    timeout=15.0,
                ).raise_for_status()
            except Exception:
                logger.exception("aging cron: failed to set last_aging_nudge_at prospect=%s", pid)

    return {"ok": True, "mode": "live", "candidates": len(candidates), "sms_sent": sent}


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
        out = send_sms(str(wa), msg)
        if not out.get("skipped"):
            sent += 1

    return {"ok": True, "candidates": len(rows), "sms_sent": sent}


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
    DEPRECATED — Charlotte automation replaced by nightly-pipeline.
    This endpoint now redirects to the nightly pipeline for backward compatibility.
    Use POST /api/crm/cron/nightly-pipeline instead.
    """
    _require_secret(x_cron_secret)
    return nightly_pipeline_run(x_cron_secret=x_cron_secret)


@router.post("/nightly-pipeline")
def nightly_pipeline_run(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    ARIA Unified Nightly Pipeline — runs at 11pm MST:
    Apify 4-actor discovery (Google Maps + LinkedIn + Leads Finder + Website Crawler)
    → Deduplicate → Bulk ZeroBounce → Domain Scan (30 concurrent) →
    Batched OpenAI (20 per call) → CASL footer + timezone scheduling →
    Store in aria_lead_inventory as 'ready'.

    Replaces the old Charlotte daily run.
    Target: complete within 90 minutes for 3,000 leads.
    """
    _require_secret(x_cron_secret)
    import asyncio
    try:
        from services.aria_lead_inventory import run_nightly_pipeline
        result = asyncio.run(run_nightly_pipeline())
        return result
    except Exception as e:
        logger.exception("nightly pipeline failed: %s", e)
        try:
            send_ceo_sms(f"ARIA nightly pipeline failed: {e!s}"[:1500])
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/morning-dispatch")
def morning_dispatch_run(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    ARIA Morning Dispatch — runs at 6:30am MST:
    Pull 'ready' leads from aria_lead_inventory ordered by score →
    Assign to vertical-specific Smartlead campaigns →
    Bulk upload with timezone-aware scheduled send times →
    Mark as 'dispatched'.

    Target: complete within 5 minutes.
    """
    _require_secret(x_cron_secret)
    try:
        from services.aria_morning_dispatch import run_morning_dispatch
        return run_morning_dispatch()
    except Exception as e:
        logger.exception("morning dispatch failed: %s", e)
        try:
            send_ceo_sms(f"ARIA morning dispatch failed: {e!s}"[:1500])
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/inbox-health")
def inbox_health_run(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    ARIA Inbox Health Monitoring — runs daily:
    Fetch email stats per sending domain from Smartlead →
    Assess bounce/spam rates (2% bounce = alert, 3% = pause; 0.1% spam = alert, 0.3% = pause) →
    Weekly MXToolbox blacklist check →
    Update aria_domain_health → Alert CEO on warnings/paused domains.
    """
    _require_secret(x_cron_secret)
    try:
        from services.aria_inbox_health import run_inbox_health_check
        # Weekly blacklist check on Mondays
        import zoneinfo
        from datetime import datetime
        mst = zoneinfo.ZoneInfo("America/Edmonton")
        include_blacklist = datetime.now(mst).weekday() == 0  # Monday
        return run_inbox_health_check(include_blacklist=include_blacklist)
    except Exception as e:
        logger.exception("inbox health check failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/daily-shield-rescan")
def daily_shield_rescan(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    2A — Daily Shield client rescan (schedule ~6am America/Denver on Railway cron).
    Rescans each active Shield client domain, diffs finding fingerprints vs last snapshot,
    alerts only on NEW critical/high via SMS (prospect phone) + email (portal profile).
    First run per client records baseline only (no alert).
    """
    _require_secret(x_cron_secret)
    try:
        return run_daily_shield_rescans()
    except Exception as e:
        logger.exception("daily shield rescan failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/weekly-threat-digest")
def weekly_threat_digest(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    Phase 2 — Weekly AI threat briefing (OpenAI) per portal client; email + portal.
    Schedule: Mondays ~14:00 UTC (~7am America/Edmonton MST in winter). Same secret as other CRM crons.
    """
    _require_secret(x_cron_secret)
    try:
        return run_weekly_threat_briefings_for_all_clients()
    except Exception as e:
        logger.exception("weekly threat digest failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/dnstwist-daily")
def dnstwist_daily(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Phase 3 — Daily dnstwist-only pass for Shield clients; WhatsApp when new registered permutations appear."""
    _require_secret(x_cron_secret)
    try:
        return run_daily_dnstwist_monitoring()
    except Exception as e:
        logger.exception("dnstwist daily failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/portal-milestones")
def portal_milestones_sweep(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Phase 2 — Award journey milestones (e.g. thirty_days_clean, hawk_certified) for all portal clients."""
    _require_secret(x_cron_secret)
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "supabase not configured"}
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=headers,
        params={"select": "client_id", "limit": "500"},
        timeout=60.0,
    )
    r.raise_for_status()
    checked = 0
    for row in r.json() or []:
        cid = row.get("client_id")
        if not cid:
            continue
        cl = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=headers,
            params={"id": f"eq.{cid}", "select": "prospect_id", "limit": "1"},
            timeout=15.0,
        )
        if cl.status_code != 200:
            continue
        crow = (cl.json() or [None])[0] or {}
        pid = crow.get("prospect_id")
        ensure_portal_milestones(str(cid), str(pid) if pid else None)
        checked += 1
    return {"ok": True, "clients_checked": checked}


@router.post("/rep-health-score")
def rep_health_score_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Phase 4 — Daily rep health scoring → profiles.health_score; CEO WhatsApp if score under 50."""
    _require_secret(x_cron_secret)
    try:
        return run_rep_health_scores()
    except Exception as e:
        logger.exception("rep health cron failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/enterprise-domain-scans")
def enterprise_domain_scans_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Phase 4 — Daily fast rescans for clients with extra monitored domains → client_domain_scans."""
    _require_secret(x_cron_secret)
    try:
        return run_enterprise_domain_scans()
    except Exception as e:
        logger.exception("enterprise domain scans failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/weekly-attacker-simulation")
def weekly_attacker_simulation_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Phase 4 — Monday narrative: OpenAI attacker simulation → client_attacker_simulation_reports."""
    _require_secret(x_cron_secret)
    try:
        return run_weekly_attacker_simulations()
    except Exception as e:
        logger.exception("attacker simulation cron failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/scheduled-ai-actions")
def scheduled_ai_actions_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """
    ARIA — execute scheduled actions where executed = false and scheduled_for <= now().
    Runs every minute via cron-job.org or Railway cron.
    Handles both legacy email actions and ARIA pipeline runs.
    """
    _require_secret(x_cron_secret)

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": True, "mode": "stub", "executed": 0}

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    now = datetime.now(timezone.utc).isoformat()

    # Fetch due actions (table renamed to aria_scheduled_actions)
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_scheduled_actions",
        headers=headers,
        params={
            "executed": "eq.false",
            "scheduled_for": f"lte.{now}",
            "select": "*",
            "limit": "50",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("aria_scheduled_actions fetch failed: %s", r.text[:300])
        return {"ok": False, "error": r.text[:300]}

    actions = r.json() or []
    executed_count = 0

    for action in actions:
        action_id = action["id"]
        action_type = action.get("action_type", "")
        payload = action.get("action_payload", {})

        try:
            if action_type == "send_email":
                _execute_scheduled_email(payload, headers)
            elif action_type == "send_reminder":
                _execute_scheduled_email(payload, headers)
            elif action_type == "run_outbound_pipeline":
                _execute_scheduled_pipeline(action, headers)
            else:
                logger.warning("Unknown scheduled action type: %s", action_type)

            # Mark as executed
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/aria_scheduled_actions",
                headers=headers,
                params={"id": f"eq.{action_id}"},
                json={"executed": True, "executed_at": datetime.now(timezone.utc).isoformat()},
                timeout=20.0,
            ).raise_for_status()
            executed_count += 1
        except Exception as exc:
            logger.exception("Failed to execute scheduled action %s: %s", action_id, exc)

    return {"ok": True, "mode": "live", "due": len(actions), "executed": executed_count}


def _execute_scheduled_email(payload: dict, headers: dict) -> None:
    """Execute a scheduled email action."""
    from services.crm_portal_email import send_resend, _wrap, _esc

    to = payload.get("to", "")
    subject = payload.get("subject", "")
    body_text = payload.get("body", "")

    if not to or not subject:
        logger.warning("Scheduled email missing 'to' or 'subject'")
        return

    inner = f"""
      <tr>
        <td style="padding:40px 48px 32px;">
          <p style="margin:0 0 24px;font-size:15px;color:#9090A8;line-height:1.6;">
            {_esc(body_text)}
          </p>
        </td>
      </tr>
"""
    send_resend(
        to_email=to,
        subject=subject,
        html=_wrap(inner),
        tags=[{"name": "category", "value": "scheduled_ai_action"}],
    )


def _execute_scheduled_pipeline(action: dict, headers: dict) -> None:
    """Execute a scheduled ARIA outbound pipeline run."""
    import threading
    from services.aria_pipeline import run_outbound_pipeline

    payload = action.get("action_payload", {})
    vertical = payload.get("vertical", "dental")
    location = payload.get("location", "Canada")
    batch_size = payload.get("batch_size", 50)
    uid = action.get("triggered_by", "")

    # Create pipeline run record
    run_payload = {
        "triggered_by": uid,
        "vertical": vertical,
        "location": location,
        "batch_size": batch_size,
        "status": "running",
        "current_step": "apify_discover",
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
        headers={**headers, "Prefer": "return=representation"},
        json=run_payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.error("Failed to create scheduled pipeline run: %s", r.text[:300])
        return

    run_data = r.json()
    run_id = run_data[0]["id"] if isinstance(run_data, list) and run_data else run_data.get("id", "")
    if not run_id:
        logger.error("Failed to get run ID for scheduled pipeline")
        return

    # Execute in background thread
    def _run() -> None:
        try:
            run_outbound_pipeline(run_id, vertical, location, batch_size)
        except Exception as exc:
            logger.exception("Scheduled pipeline run failed: %s", exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("Scheduled ARIA pipeline run started: %s (vertical=%s, location=%s)", run_id, vertical, location)


@router.post("/aria-memory-ingestion")
def aria_memory_ingestion_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """ARIA Phase 4 — Every 15 minutes: ingest recent CRM events into semantic memory."""
    _require_secret(x_cron_secret)
    try:
        return run_memory_ingestion()
    except Exception as e:
        logger.exception("aria memory ingestion cron failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/aria-client-health")
def aria_client_health_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """ARIA Phase 3 — Every 15 minutes: update client health scores, flag at-risk, push alerts."""
    _require_secret(x_cron_secret)
    try:
        return run_client_health_scores()
    except Exception as e:
        logger.exception("aria client health cron failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/aria-monday-briefing")
def aria_monday_briefing_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """ARIA Phase 3 — Every Monday 8am: generate CEO/HoS business briefing."""
    _require_secret(x_cron_secret)
    try:
        return run_monday_briefing()
    except Exception as e:
        logger.exception("aria monday briefing cron failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/aria-competitive-brief")
def aria_competitive_brief_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """ARIA Phase 3 — Weekly: generate competitive intelligence brief for CEO."""
    _require_secret(x_cron_secret)
    try:
        return run_competitive_brief()
    except Exception as e:
        logger.exception("aria competitive brief cron failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e
# scanner-health, va-reply-escalation, charlotte-quality-check live in routers/crm_scale.cron_routes (mounted in main.py).
