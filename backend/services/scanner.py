"""Call HAWK scanner relay (hawk-scanner-v2 on Railway)."""
from __future__ import annotations

import logging
import time

import httpx

from config import SCANNER_RELAY_URL, SCANNER_TIMEOUT

logger = logging.getLogger(__name__)

_TRUST_LEVELS = frozenset({"public", "subscriber", "certified"})


def _normalize_trust_level(raw: str | None) -> str:
    x = (raw or "public").strip().lower()
    return x if x in _TRUST_LEVELS else "public"


def enqueue_async_scan(
    domain: str,
    industry: str | None = None,
    company_name: str | None = None,
    scan_depth: str = "full",
    trust_level: str = "public",
) -> str:
    """POST /v1/scan/async — returns job_id (do not pass prospect_id; CRM persists via finalize)."""
    url = f"{SCANNER_RELAY_URL.rstrip('/')}/v1/scan/async"
    body: dict = {
        "domain": domain,
        "scan_depth": scan_depth or "full",
        "trust_level": _normalize_trust_level(trust_level),
    }
    if industry and industry.strip():
        body["industry"] = industry.strip()
    if company_name and company_name.strip():
        body["company_name"] = company_name.strip()
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    job_id = data.get("job_id")
    if not job_id:
        raise RuntimeError("Scanner enqueue returned no job_id")
    return str(job_id)


def get_async_job(job_id: str) -> dict:
    """GET /v1/jobs/{id} — status, result, or error."""
    url = f"{SCANNER_RELAY_URL.rstrip('/')}/v1/jobs/{job_id}"
    with httpx.Client(timeout=45.0) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()


def poll_scan_job(
    job_id: str,
    *,
    timeout_sec: float = 720.0,
    interval_sec: float = 3.0,
) -> dict:
    """Block until job completes or times out. Returns scanner result dict (same shape as /scan)."""
    deadline = time.monotonic() + timeout_sec
    last_status = None
    while time.monotonic() < deadline:
        j = get_async_job(job_id)
        st = j.get("status")
        last_status = st
        if st == "complete":
            result = j.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("scan complete but no result payload")
            return result
        if st == "failed":
            raise RuntimeError(str(j.get("error") or "scan job failed"))
        time.sleep(interval_sec)
    raise TimeoutError(f"scan job {job_id} timed out after {timeout_sec}s (last={last_status})")


def run_dnstwist_scan(domain: str, *, trust_level: str = "public") -> dict:
    """POST dnstwist-only job (lookalike monitoring)."""
    url = f"{SCANNER_RELAY_URL.rstrip('/')}/v1/scan/dnstwist"
    with httpx.Client(timeout=min(SCANNER_TIMEOUT, 180.0)) as client:
        r = client.post(
            url,
            json={"domain": domain.strip().lower(), "trust_level": _normalize_trust_level(trust_level)},
        )
        r.raise_for_status()
        return r.json()


def run_scan(
    domain: str,
    scan_id: str | None = None,
    *,
    scan_depth: str = "full",
    trust_level: str = "public",
) -> dict:
    """
    POST to scanner relay; returns scan response (score, grade, findings).
    scan_depth: "full" (all layers) or "fast" (lighter / quicker pass).
    Raises httpx.HTTPStatusError on 4xx/5xx, httpx.ConnectError if relay unreachable.
    """
    depth = (scan_depth or "full").strip().lower()
    if depth not in ("full", "fast"):
        depth = "full"
    url = f"{SCANNER_RELAY_URL.rstrip('/')}/scan"
    try:
        with httpx.Client(timeout=SCANNER_TIMEOUT) as client:
            r = client.post(
                url,
                json={
                    "domain": domain,
                    "scan_id": scan_id,
                    "scan_depth": depth,
                    "trust_level": _normalize_trust_level(trust_level),
                },
            )
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError as e:
        logger.error("Scanner relay unreachable at %s: %s", url, e)
        raise
    except httpx.TimeoutException as e:
        logger.error("Scanner relay timeout at %s after %ss: %s", url, SCANNER_TIMEOUT, e)
        raise
