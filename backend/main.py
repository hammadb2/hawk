"""
HAWK Core API — FastAPI app with auth, scans, domains, reports, billing, Ask HAWK, agency, notifications.
SQLite (dev) / PostgreSQL (prod). JWT auth. Stripe webhooks. Scanner via Ghost relay.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import auth, scans, findings, domains, reports, billing, hawk, agency, notifications, breach_check
from backend.routers import (
    crm_prospects,
    crm_clients,
    crm_commissions,
    crm_charlotte,
    crm_stripe_webhooks,
    crm_tickets,
    crm_users,
    crm_reports,
    crm_sync,
    crm_product_commands,
    crm_inbound,
    crm_apollo,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    # shutdown if needed


def _register_crm_scheduler(app: FastAPI) -> None:
    from backend.routers.crm_sync import register_sync_scheduler
    register_sync_scheduler(app)


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

# CRM routers
app.include_router(crm_prospects.router)
app.include_router(crm_clients.router)
app.include_router(crm_commissions.router)
app.include_router(crm_charlotte.router)
app.include_router(crm_stripe_webhooks.router)
app.include_router(crm_tickets.router)
app.include_router(crm_users.router)
app.include_router(crm_reports.router)
app.include_router(crm_sync.router)
app.include_router(crm_product_commands.router)
app.include_router(crm_inbound.router)
app.include_router(crm_apollo.router)

_register_crm_scheduler(app)


@app.get("/health")
def health():
    return {"status": "ok", "service": "hawk-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
