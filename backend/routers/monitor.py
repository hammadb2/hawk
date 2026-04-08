"""Self-healing monitor — cron-triggered integration health checks."""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Header, HTTPException

from services.health_monitor import run_health_monitor
from services.scanner_health_service import run_scanner_health_check

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
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, CRON_SECRET):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/health-check")
def monitor_health_check(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Run all integration checks, log to system_health_log, alert CEO on consecutive failures."""
    _require_secret(x_cron_secret)
    return run_health_monitor()


@router.post("/scanner-health")
def monitor_scanner_health(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    """Queue depth, failure rate, log to scanner_health_logs, WhatsApp CEO if thresholds exceeded."""
    _require_secret(x_cron_secret)
    return run_scanner_health_check()
