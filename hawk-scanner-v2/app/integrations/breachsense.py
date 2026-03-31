"""Breachsense API — placeholder; set BREACHSENSE_API_KEY and base URL when contract is wired."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def check_domain(domain: str, api_key: str, base_url: str) -> dict[str, Any]:
    if not api_key:
        return {"layer": "breachsense", "skipped": True, "reason": "no BREACHSENSE_API_KEY"}
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return {"layer": "breachsense", "skipped": True, "reason": "no BREACHSENSE_BASE_URL"}
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.post(
            f"{base}/domain-scan",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"domain": domain.lower().strip()},
        )
    if r.status_code >= 400:
        logger.warning("breachsense http %s: %s", r.status_code, r.text[:300])
        return {"layer": "breachsense", "error": f"http_{r.status_code}"}
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:2000]}
    return {"layer": "breachsense", "data": data}
