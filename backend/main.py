"""
HAWK Core API — FastAPI app with auth, scans, domains, reports, billing, Ask HAWK, agency, notifications.
SQLite (dev) / PostgreSQL (prod). JWT auth. Stripe webhooks. Scanner via Ghost relay.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_CORS_ORIGINS_RAW = os.environ.get("HAWK_CORS_ORIGINS", "").strip()
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()] if _CORS_ORIGINS_RAW else ["*"]

from routers import auth, scans, findings, domains, reports, billing, hawk, agency, notifications, breach_check, marketing, guarantee_access
from routers import (
    aria_api,
    aria_pipeline,
    aria_voice,
    aria_whatsapp,
    crm_ai_command,
    crm_client_portal,
    crm_cron,
    crm_dashboard,
    crm_enterprise,
    crm_invite,
    crm_mailboxes,
    crm_onboarding,
    crm_va,
    crm_payment,
    crm_portal_api,
    crm_scale,
    crm_settings as crm_settings_router,
    crm_webhooks,
    guardian,
    monitor,
    portal_phase2,
    portal_self_serve,
)

from services.crm_apscheduler_jobs import (
    run_aging_job,
    run_aria_client_health_job,
    run_aria_memory_job,
    run_attacker_sim_job,
    run_competitive_brief_job,
    run_dnstwist_job,
    run_enterprise_scans_job,
    run_inbox_health_job,
    run_monday_briefing_job,
    run_monthly_reports_job,
    run_mailbox_daily_reset_job,
    run_mailbox_imap_poller_job,
    run_aria_scheduled_actions_job,
    run_morning_dispatch_job,
    run_nightly_pipeline_job,
    run_onboarding_drip_job,
    run_pipeline_doctor_job,
    run_portal_milestones_job,
    run_rep_health_job,
    run_rolling_dispatch_job,
    run_scheduled_ai_actions_job,
    run_shield_rescan_job,
    run_sla_auto_scan_job,
    run_stale_pipeline_job,
    run_weekly_threat_job,
)

if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1, send_default_pii=False)
    except ImportError:
        pass


MST = ZoneInfo("America/New_York")
# Dispatch-critical jobs run on US Eastern Time so outbound email lands in
# prospect business hours. Internal / rep-facing jobs stay on MST (Jamie's TZ).
ET = ZoneInfo("America/New_York")
scheduler = AsyncIOScheduler(timezone=MST)

scheduler.add_job(run_nightly_pipeline_job, CronTrigger(hour=23, minute=0, timezone=MST))
scheduler.add_job(run_morning_dispatch_job, CronTrigger(hour=6, minute=30, timezone=MST))
scheduler.add_job(run_inbox_health_job, CronTrigger(hour=7, minute=0, timezone=MST))
scheduler.add_job(run_aging_job, CronTrigger(minute=0, timezone=MST))
scheduler.add_job(run_stale_pipeline_job, CronTrigger(hour="*/6", minute=0, timezone=MST))
scheduler.add_job(run_onboarding_drip_job, CronTrigger(hour=8, minute=0, timezone=MST))
scheduler.add_job(run_shield_rescan_job, CronTrigger(hour=9, minute=0, timezone=MST))
scheduler.add_job(run_dnstwist_job, CronTrigger(hour=10, minute=0, timezone=MST))
scheduler.add_job(run_portal_milestones_job, CronTrigger(hour=11, minute=0, timezone=MST))
scheduler.add_job(run_rep_health_job, CronTrigger(hour=12, minute=0, timezone=MST))
scheduler.add_job(run_enterprise_scans_job, CronTrigger(hour=13, minute=0, timezone=MST))
scheduler.add_job(run_monthly_reports_job, CronTrigger(day=1, hour=7, minute=0, timezone=MST))
scheduler.add_job(run_weekly_threat_job, CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=MST))
scheduler.add_job(run_attacker_sim_job, CronTrigger(day_of_week="mon", hour=7, minute=30, timezone=MST))
scheduler.add_job(run_monday_briefing_job, CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=MST))
scheduler.add_job(run_competitive_brief_job, CronTrigger(day_of_week="mon", hour=8, minute=30, timezone=MST))
scheduler.add_job(run_scheduled_ai_actions_job, CronTrigger(minute="*/15", timezone=MST))
scheduler.add_job(run_aria_memory_job, CronTrigger(minute="*/15", timezone=MST))
scheduler.add_job(run_aria_client_health_job, CronTrigger(minute="*/15", timezone=MST))
scheduler.add_job(run_sla_auto_scan_job, CronTrigger(minute="*/2", timezone=MST))
# Rolling email dispatcher — 9am through 4pm ET (8 ticks) toward 200/campaign/day (600/day).
scheduler.add_job(run_rolling_dispatch_job, CronTrigger(hour="9-16", minute=5, timezone=ET))
# ARIA Pipeline Doctor — every 15 min, diagnoses stuck buckets (new / scanning /
# scanned / ready / apollo credits) and auto-applies idempotent escape hatches.
# Escalates critical buckets via CEO SMS.
scheduler.add_job(run_pipeline_doctor_job, CronTrigger(minute="*/15", timezone=MST))
# Mailbox-native dispatcher: poll IMAP inboxes for replies every 2 min and reset
# per-mailbox daily send counters at midnight ET (matches dispatcher day boundary).
# Interval is driven by the ≤5-minute autonomous-reply SLA we promise US
# prospects: detection + classify + draft + SMTP send must complete within
# 5 min end-to-end. At */5 the worst-case detection latency alone consumed the
# entire budget; */2 keeps median ≈1 min and worst case ≤2 min + send time.
scheduler.add_job(run_mailbox_imap_poller_job, CronTrigger(minute="*/2", timezone=MST))
scheduler.add_job(run_mailbox_daily_reset_job, CronTrigger(hour=0, minute=0, timezone=ET))
# Autonomous reply loop: drain the aria_scheduled_actions queue every 5 min.
# Handles 48hr follow-ups, 24hr call reminders, weekly nurture drips, OOO
# return follow-ups, and 90-day snoozes.
scheduler.add_job(run_aria_scheduled_actions_job, CronTrigger(minute="*/5", timezone=MST))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Register autonomous-reply scheduled-action handlers before the
    # scheduler starts, so the very first tick has handlers available.
    try:
        from services import aria_nurture

        aria_nurture.register_handlers()
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Failed to register ARIA nurture handlers")

    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="HAWK API",
    description="B2B cybersecurity SaaS for US SMBs — attack surface scans, dashboard, Ask HAWK, billing.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True if _CORS_ORIGINS != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(scans.router)
app.include_router(findings.router)
app.include_router(domains.router)
app.include_router(reports.router)
app.include_router(billing.router)
app.include_router(hawk.router)
app.include_router(agency.router)
app.include_router(notifications.router)
app.include_router(breach_check.router)
app.include_router(marketing.router)
app.include_router(guarantee_access.router)
app.include_router(crm_cron.router)
app.include_router(crm_webhooks.router)
app.include_router(crm_portal_api.router)
app.include_router(crm_client_portal.router)
app.include_router(crm_enterprise.router)
app.include_router(portal_phase2.router)
app.include_router(portal_self_serve.router)
app.include_router(crm_scale.router)
app.include_router(crm_dashboard.router)
app.include_router(crm_settings_router.router)
app.include_router(crm_scale.cron_routes)
app.include_router(crm_invite.router)
app.include_router(crm_mailboxes.router)
app.include_router(crm_onboarding.router)
app.include_router(crm_va.router)
app.include_router(crm_ai_command.router)
app.include_router(aria_pipeline.router)
app.include_router(aria_voice.router)
app.include_router(aria_whatsapp.router)
app.include_router(aria_api.router)
app.include_router(crm_payment.router)
app.include_router(monitor.router)
app.include_router(guardian.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "hawk-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
