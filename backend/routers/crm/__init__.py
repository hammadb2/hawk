"""CRM router — aggregates all CRM sub-routers under /api/crm."""
from fastapi import APIRouter

from backend.routers.crm import (
    dashboard,
    prospects,
    clients,
    activities,
    tasks,
    team,
    scoreboard,
    charlotte,
    commissions,
    reports,
    settings,
)

crm_router = APIRouter(prefix="/api/crm", tags=["CRM"])

crm_router.include_router(dashboard.router)
crm_router.include_router(prospects.router)
crm_router.include_router(clients.router)
crm_router.include_router(activities.router)
crm_router.include_router(tasks.router)
crm_router.include_router(team.router)
crm_router.include_router(scoreboard.router)
crm_router.include_router(charlotte.router)
crm_router.include_router(commissions.router)
crm_router.include_router(reports.router)
crm_router.include_router(settings.router)
