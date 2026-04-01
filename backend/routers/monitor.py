"""Self-healing monitor — cron-triggered integration health checks."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException

from services.health_monitor import run_health_monitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

CRON_SECRET = (
    os.environ.get("HAWK_CRM_CRON_SECRET", "").strip()
    or os.environ.get("HAWK_CRON_SECRET", "").strip()
    or os.environ.get("CRON_SECRET", "").strip()
)


def _require_secret(x_cron_secret: str | None) -> None:
    if not CRON_SECRET:
        logger.warning("Monitor: cron secret not configured — rejecting")
        raise HTTPException(status_code=503, detail="Monitor not configured")
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/health-check")
def monitor_health_check(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Run all integration checks, log to system_health_log, alert CEO on consecutive failures."""
    _require_secret(x_cron_secret)
    return run_health_monitor()
