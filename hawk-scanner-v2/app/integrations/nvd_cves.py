"""Map WhatWeb fingerprints to NVD CVE awareness (supply chain risk)."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

import httpx

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

TECH_KEYWORDS: tuple[str, ...] = (
    "wordpress",
    "drupal",
    "joomla",
    "magento",
    "apache",
    "nginx",
    "microsoft-iis",
    "iis",
    "openssl",
    "php",
    "jquery",
    "jenkins",
    "gitlab",
    "tomcat",
    "django",
    "rails",
    "nodejs",
    "react",
    "angular",
    "vue.js",
    "shopify",
    "woocommerce",
)


def _extract_keywords(lines: list[str]) -> list[str]:
    blob = "\n".join(lines).lower()
    found: list[str] = []
    for k in TECH_KEYWORDS:
        if k in blob:
            label = k.replace("-", " ").title()
            if label not in found:
                found.append(label)
        if len(found) >= 4:
            break
    return found


async def _nvd_keyword_search(kw: str, settings: Settings) -> list[str]:
    params: dict[str, Any] = {"keywordSearch": kw, "resultsPerPage": 5}
    key = (getattr(settings, "nvd_api_key", None) or os.environ.get("NVD_API_KEY", "") or "").strip()
    if key:
        params["apiKey"] = key
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(NVD_URL, params=params)
    except Exception as e:
        logger.warning("NVD request failed for %s: %s", kw, e)
        return []
    if r.status_code == 403:
        logger.warning("NVD 403 for %s — set NVD_API_KEY", kw)
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    vulns = data.get("vulnerabilities") or []
    cve_ids: list[str] = []
    for v in vulns[:5]:
        cve = (v.get("cve") or {}).get("id")
        if cve:
            cve_ids.append(str(cve))
    return cve_ids


async def nvd_findings_from_whatweb(
    whatweb_lines: list[str],
    domain: str,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """
    Query NIST NVD for up to two distinct stack components from WhatWeb (separate findings).
    Without NVD_API_KEY, sleeps ~6.5s between calls to respect public rate limits.
    """
    settings = settings or get_settings()
    if os.environ.get("HAWK_NVD_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return []
    kws = _extract_keywords(whatweb_lines)
    if not kws:
        return []

    has_key = bool((getattr(settings, "nvd_api_key", None) or os.environ.get("NVD_API_KEY", "") or "").strip())
    out: list[dict[str, Any]] = []
    for i, kw in enumerate(kws[:2]):
        if i > 0 and not has_key:
            await asyncio.sleep(6.5)
        cve_ids = await _nvd_keyword_search(kw, settings)
        if not cve_ids:
            continue
        sev = "medium" if len(cve_ids) >= 2 else "low"
        desc = (
            f"NIST NVD lists CVE records when searching for **{kw}**, which appears in your "
            f"fingerprint for `{domain}`. Verify your exact version against vendor advisories — "
            "not every CVE applies."
        )
        out.append(
            {
                "id": str(uuid.uuid4()),
                "severity": sev,
                "category": "Supply chain",
                "title": f"NVD: known CVEs related to {kw} (fingerprint)",
                "description": desc,
                "technical_detail": ", ".join(cve_ids[:5]),
                "affected_asset": domain,
                "remediation": f"Confirm installed versions of {kw}; patch; re-scan after updates.",
                "layer": "nvd_supply_chain",
                "compliance": ["Vendor patch management"],
            }
        )
    return out
