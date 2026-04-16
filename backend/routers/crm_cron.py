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
from services.crm_charlotte_run import run_charlotte_daily
from services.crm_shield_daily import run_daily_shield_rescans
from services.crm_openphone import format_aging_deal_message, format_stale_deal_message, send_ceo_sms, send_sms
from routers.portal_phase2 import run_weekly_threat_briefings_for_all_clients
from services.crm_dnstwist_daily import run_daily_dnstwist_monitoring
from services.crm_rep_health import run_rep_health_scores
from services.crm_enterprise_domain_scans import run_enterprise_domain_scans
from services.crm_attacker_simulation import run_weekly_attacker_simulations
from services.portal_milestones import ensure_portal_milestones

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
    Charlotte automation — daily ~8am MST via cron-job.org:
    Apollo (200) → ZeroBounce → suppressions + CRM dedupe → Scanner (10 concurrent) → OpenAI → Smartlead → charlotte_runs + CEO SMS (OpenPhone).

    Header: X-Cron-Secret (same as other CRM crons: HAWK_CRM_CRON_SECRET / HAWK_CRON_SECRET / CRON_SECRET).
    Set CHARLOTTE_AUTOMATION_DRY_RUN=1 on the API to skip external calls (smoke test).
    """
    _require_secret(x_cron_secret)
    try:
        return run_charlotte_daily()
    except Exception as e:
        logger.exception("charlotte run failed: %s", e)
        try:
            send_ceo_sms(f"Charlotte run failed: {e!s}"[:1500])
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
    AI Command Center — execute scheduled actions where executed = false and scheduled_for <= now().
    Runs every minute via cron-job.org or Railway cron.
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

    # Fetch due actions
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/scheduled_ai_actions",
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
        logger.warning("scheduled_ai_actions fetch failed: %s", r.text[:300])
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
            else:
                logger.warning("Unknown scheduled action type: %s", action_type)

            # Mark as executed
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/scheduled_ai_actions",
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


# scanner-health, va-reply-escalation, charlotte-quality-check live in routers/crm_scale.cron_routes (mounted in main.py).
