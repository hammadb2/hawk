"""Breachsense API — stealer / credential exposure (2C)."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def check_domain(domain: str, api_key: str, base_url: str) -> dict[str, Any]:
    if not api_key:
        return {"layer": "breachsense", "skipped": True, "reason": "no BREACHSENSE_API_KEY"}
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return {"layer": "breachsense", "skipped": True, "reason": "no BREACHSENSE_BASE_URL"}

    domain_clean = domain.lower().strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=50.0) as client:
        # Primary: documented-style domain scan
        r = await client.post(
            f"{base}/domain-scan",
            headers=headers,
            json={"domain": domain_clean},
        )
        if r.status_code == 404:
            r = await client.post(
                f"{base}/v1/domain-scan",
                headers=headers,
                json={"domain": domain_clean},
            )

    if r.status_code >= 400:
        logger.warning("breachsense http %s: %s", r.status_code, r.text[:400])
        return {"layer": "breachsense", "error": f"http_{r.status_code}", "body_preview": r.text[:500]}

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:4000]}

    return {"layer": "breachsense", "data": data}


def findings_from_breachsense(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn Breachsense JSON into HAWK findings (stealer narrative)."""
    if summary.get("skipped") or summary.get("error"):
        return []

    data = summary.get("data")
    if not isinstance(data, dict):
        return []

    out: list[dict[str, Any]] = []
    rows: list[Any] = []

    for key in (
        "stealer_logs",
        "stealer_matches",
        "stealer_results",
        "credentials",
        "results",
        "records",
        "matches",
        "data",
    ):
        chunk = data.get(key)
        if isinstance(chunk, list):
            rows.extend(chunk)
        elif isinstance(chunk, dict) and isinstance(chunk.get("items"), list):
            rows.extend(chunk["items"])

    if not rows and isinstance(data.get("count"), int) and data["count"] > 0:
        out.append(
            {
                "id": str(uuid.uuid4()),
                "severity": "critical",
                "category": "Stealer exposure",
                "title": "Breachsense reported domain-related stealer activity",
                "description": (
                    "Our dark-web partner reported exposure tied to your domain. "
                    "Malware-stolen credentials often appear here before public breach databases."
                ),
                "technical_detail": str(data)[:3500],
                "affected_asset": domain,
                "remediation": (
                    "Force-reset affected passwords, roll session tokens, enforce MFA, and isolate any listed endpoints. "
                    "Review devices for malware."
                ),
                "layer": "breachsense",
            }
        )
        return out

    for row in rows[:25]:
        if not isinstance(row, dict):
            continue
        email = row.get("email") or row.get("username") or row.get("user") or "An account"
        days = row.get("days_ago") or row.get("days") or row.get("discovered_days_ago")
        svc = row.get("service") or row.get("application") or row.get("url") or "a business system"
        days_txt = f"{days} days ago" if days is not None else "recently"

        out.append(
            {
                "id": str(uuid.uuid4()),
                "severity": "critical",
                "category": "Stealer exposure",
                "title": f"Possible stolen credential for {email}",
                "description": (
                    f"Breachsense indicates a credential associated with your organization appeared in stealer logs "
                    f"about {days_txt}. This often means malware on a workstation captured the password."
                ),
                "technical_detail": str(row)[:3000],
                "affected_asset": str(email),
                "remediation": (
                    f"Reset the password for {email} immediately, enable MFA, and scan the device used for that account. "
                    "Assume the password is known to criminals until rotated."
                ),
                "layer": "breachsense",
            }
        )

    return out
