"""Call Ghost scanner relay (which forwards to Specter)."""
from __future__ import annotations

import httpx

from backend.config import SCANNER_RELAY_URL, SCANNER_TIMEOUT


def run_scan(domain: str, scan_id: str | None = None) -> dict:
    """
    POST to Ghost relay; returns full scan response (score, grade, findings).
    Raises httpx.HTTPStatusError on 4xx/5xx, httpx.ConnectError if relay unreachable.
    """
    url = f"{SCANNER_RELAY_URL.rstrip('/')}/scan"
    with httpx.Client(timeout=SCANNER_TIMEOUT) as client:
        r = client.post(url, json={"domain": domain, "scan_id": scan_id})
        r.raise_for_status()
        return r.json()
