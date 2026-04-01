"""
HAWK Core API — FastAPI app with auth, scans, domains, reports, billing, Ask HAWK, agency, notifications.
SQLite (dev) / PostgreSQL (prod). JWT auth. Stripe webhooks. Scanner via Ghost relay.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import auth, scans, findings, domains, reports, billing, hawk, agency, notifications, breach_check
from routers import crm_cron, crm_portal_api, crm_webhooks, monitor

if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1, send_default_pii=False)
    except ImportError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    # shutdown if needed


app = FastAPI(
    title="HAWK API",
    description="B2B cybersecurity SaaS for Canadian SMBs — attack surface scans, dashboard, Ask HAWK, billing.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
app.include_router(crm_cron.router)
app.include_router(crm_webhooks.router)
app.include_router(crm_portal_api.router)
app.include_router(monitor.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "hawk-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
