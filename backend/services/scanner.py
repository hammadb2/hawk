"""Call Ghost scanner relay (which forwards to Specter)."""
from __future__ import annotations

import logging

import httpx

from config import SCANNER_RELAY_URL, SCANNER_TIMEOUT

logger = logging.getLogger(__name__)


def run_scan(domain: str, scan_id: str | None = None) -> dict:
    """
    POST to Ghost relay; returns full scan response (score, grade, findings).
    Raises httpx.HTTPStatusError on 4xx/5xx, httpx.ConnectError if relay unreachable.
    """
    url = f"{SCANNER_RELAY_URL.rstrip('/')}/scan"
    try:
        with httpx.Client(timeout=SCANNER_TIMEOUT) as client:
            r = client.post(url, json={"domain": domain, "scan_id": scan_id})
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError as e:
        logger.error("Scanner relay unreachable at %s: %s", url, e)
        raise
    except httpx.TimeoutException as e:
        logger.error("Scanner relay timeout at %s after %ss: %s", url, SCANNER_TIMEOUT, e)
        raise
