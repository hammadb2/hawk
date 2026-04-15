"""
HAWK Core API — FastAPI app with auth, scans, domains, reports, billing, Ask HAWK, agency, notifications.
SQLite (dev) / PostgreSQL (prod). JWT auth. Stripe webhooks. Scanner via Ghost relay.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_CORS_ORIGINS_RAW = os.environ.get("HAWK_CORS_ORIGINS", "").strip()
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()] if _CORS_ORIGINS_RAW else ["*"]

from routers import auth, scans, findings, domains, reports, billing, hawk, agency, notifications, breach_check, marketing, guarantee_access
from routers import (
    crm_client_portal,
    crm_cron,
    crm_enterprise,
    crm_invite,
    crm_payment,
    crm_portal_api,
    crm_scale,
    crm_team_docs,
    crm_va,
    crm_webhooks,
    monitor,
    portal_phase2,
    portal_self_serve,
)

if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1, send_default_pii=False)
    except ImportError:
        pass


app = FastAPI(
    title="HAWK API",
    description="B2B cybersecurity SaaS for Canadian SMBs — attack surface scans, dashboard, Ask HAWK, billing.",
    version="1.0.0",
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
app.include_router(crm_scale.cron_routes)
app.include_router(crm_invite.router)
app.include_router(crm_payment.router)
app.include_router(crm_va.router)
app.include_router(crm_team_docs.router)
app.include_router(monitor.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "hawk-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
