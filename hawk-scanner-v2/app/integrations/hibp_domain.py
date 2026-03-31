"""HIBP domain breach exposure (API v3) — counts only; no raw emails in output."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

HIBP_BASE = "https://haveibeenpwned.com/api/v3"


async def check_domain(domain: str, api_key: str) -> dict[str, Any]:
    if not api_key:
        return {"layer": "hibp_domain", "skipped": True, "reason": "no HIBP_API_KEY"}
    domain = domain.lower().strip()
    headers = {
        "hibp-api-key": api_key,
        "user-agent": "HAWK-Scanner-2/1.0",
    }
    url = f"{HIBP_BASE}/breacheddomain/{domain}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers)
    if r.status_code == 404:
        return {"layer": "hibp_domain", "exposed_accounts": 0, "note": "none reported"}
    if r.status_code == 401:
        return {"layer": "hibp_domain", "error": "invalid_api_key"}
    r.raise_for_status()
    data = r.json()
    # API returns a list of email addresses — do not persist addresses
    count = len(data) if isinstance(data, list) else 0
    return {"layer": "hibp_domain", "exposed_accounts": count, "pii_redacted": True}


def findings_from_hibp(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    import uuid

    if summary.get("skipped") or summary.get("error"):
        return []
    n = int(summary.get("exposed_accounts") or 0)
    if n <= 0:
        return []
    sev = "high" if n >= 10 else "medium"
    return [
        {
            "id": str(uuid.uuid4()),
            "severity": sev,
            "category": "Breach Exposure",
            "title": "Domain emails appeared in known breaches",
            "description": f"HIBP reports {n} address(es) on this domain in prior breaches (details withheld).",
            "technical_detail": "Have I Been Pwned domain search",
            "affected_asset": domain,
            "remediation": "Force password resets, enforce MFA, and monitor stealer logs.",
            "layer": "hibp_domain",
        }
    ]
