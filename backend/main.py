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
    crm_onboarding,
    crm_payment,
    crm_portal_api,
    crm_scale,
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
    run_morning_dispatch_job,
    run_nightly_pipeline_job,
    run_onboarding_drip_job,
    run_portal_milestones_job,
    run_rep_health_job,
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


MST = ZoneInfo("America/Edmonton")
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="HAWK API",
    description="B2B cybersecurity SaaS for Canadian SMBs — attack surface scans, dashboard, Ask HAWK, billing.",
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
app.include_router(crm_scale.cron_routes)
app.include_router(crm_invite.router)
app.include_router(crm_onboarding.router)
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
