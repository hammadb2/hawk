"""Version-aware NVD CVE matching from WhatWeb fingerprints.

Extracts technology **name + version** from WhatWeb output, queries NVD for
that specific product, and checks whether the detected version falls inside
the affected version ranges reported by each CVE.  Findings include the exact
version detected, matching CVE IDs, CVSS scores, and patched versions.

Falls back to keyword-only search when no version can be extracted (original
behaviour).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
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

# Regex patterns for extracting version strings from WhatWeb output.
# WhatWeb lines look like:  "WordPress[5.9.3]" or "Apache[2.4.51]"
_VERSION_RE = re.compile(
    r"(?P<tech>[A-Za-z][A-Za-z0-9._-]+)\[(?P<version>\d+(?:\.\d+){1,4})\]"
)

# Fallback: "Apache/2.4.51" style
_SLASH_VERSION_RE = re.compile(
    r"(?P<tech>[A-Za-z][A-Za-z0-9._-]+)/(?P<version>\d+(?:\.\d+){1,4})"
)


def _parse_version_tuple(v: str) -> tuple[int, ...]:
    """Parse '2.4.51' → (2, 4, 51)."""
    parts: list[int] = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def _version_in_range(
    ver: str,
    start_inc: str | None,
    start_exc: str | None,
    end_inc: str | None,
    end_exc: str | None,
) -> bool:
    """Return True if *ver* falls inside the CPE version range."""
    vt = _parse_version_tuple(ver)
    if start_inc:
        if vt < _parse_version_tuple(start_inc):
            return False
    if start_exc:
        if vt <= _parse_version_tuple(start_exc):
            return False
    if end_inc:
        if vt > _parse_version_tuple(end_inc):
            return False
    if end_exc:
        if vt >= _parse_version_tuple(end_exc):
            return False
    return True


def _extract_versioned_techs(lines: list[str]) -> list[dict[str, str]]:
    """Return list of {tech, version, label} dicts from WhatWeb output."""
    blob = "\n".join(lines)
    found: dict[str, dict[str, str]] = {}
    for m in _VERSION_RE.finditer(blob):
        tech = m.group("tech").lower().strip(".-_")
        ver = m.group("version")
        key = f"{tech}:{ver}"
        if key not in found:
            found[key] = {"tech": tech, "version": ver, "label": m.group("tech")}
    for m in _SLASH_VERSION_RE.finditer(blob):
        tech = m.group("tech").lower().strip(".-_")
        ver = m.group("version")
        key = f"{tech}:{ver}"
        if key not in found:
            found[key] = {"tech": tech, "version": ver, "label": m.group("tech")}
    return list(found.values())[:6]


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


def _extract_cvss(cve_item: dict[str, Any]) -> tuple[float | None, str]:
    """Best-effort CVSS score + vector from NVD cve object."""
    metrics = cve_item.get("metrics") or {}
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key)
        if not entries or not isinstance(entries, list):
            continue
        for entry in entries:
            cvss = entry.get("cvssData") or {}
            score = cvss.get("baseScore")
            vector = cvss.get("vectorString") or ""
            if score is not None:
                return float(score), vector
    return None, ""


def _extract_fix_version(configs: list[dict[str, Any]]) -> str | None:
    """Try to find the 'versionEndExcluding' as the patched version."""
    for conf in configs:
        for node in conf.get("nodes") or []:
            for match in node.get("cpeMatch") or []:
                end_exc = match.get("versionEndExcluding")
                if end_exc:
                    return str(end_exc)
    return None


async def _nvd_versioned_search(
    tech: str,
    version: str,
    label: str,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Query NVD for a technology keyword and filter CVEs matching the detected version."""
    params: dict[str, Any] = {"keywordSearch": tech, "resultsPerPage": 20}
    key = (getattr(settings, "nvd_api_key", None) or os.environ.get("NVD_API_KEY", "") or "").strip()
    if key:
        params["apiKey"] = key
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(NVD_URL, params=params)
    except Exception as e:
        logger.warning("NVD versioned request failed for %s: %s", tech, e)
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []

    vulns = data.get("vulnerabilities") or []
    matched: list[dict[str, Any]] = []
    for v in vulns:
        cve_obj = v.get("cve") or {}
        cve_id = cve_obj.get("id")
        if not cve_id:
            continue
        configs = cve_obj.get("configurations") or []
        version_hit = False
        fix_ver: str | None = None
        for conf in configs:
            for node in conf.get("nodes") or []:
                for cm in node.get("cpeMatch") or []:
                    if not cm.get("vulnerable", False):
                        continue
                    cpe_uri = (cm.get("criteria") or "").lower()
                    if tech.lower().replace("-", "").replace("_", "") not in cpe_uri.replace("-", "").replace("_", ""):
                        continue
                    si = cm.get("versionStartIncluding")
                    se = cm.get("versionStartExcluding")
                    ei = cm.get("versionEndIncluding")
                    ee = cm.get("versionEndExcluding")
                    if si or se or ei or ee:
                        if _version_in_range(version, si, se, ei, ee):
                            version_hit = True
                            if ee:
                                fix_ver = ee
                    elif version in cpe_uri:
                        version_hit = True

        if version_hit:
            cvss_score, cvss_vector = _extract_cvss(cve_obj)
            if not fix_ver:
                fix_ver = _extract_fix_version(configs)
            matched.append({
                "cve_id": cve_id,
                "cvss_score": cvss_score,
                "cvss_vector": cvss_vector,
                "fix_version": fix_ver,
            })
        if len(matched) >= 5:
            break
    return matched


async def nvd_findings_from_whatweb(
    whatweb_lines: list[str],
    domain: str,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Version-aware NVD matching with fallback to keyword search."""
    settings = settings or get_settings()
    if os.environ.get("HAWK_NVD_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return []

    has_key = bool((getattr(settings, "nvd_api_key", None) or os.environ.get("NVD_API_KEY", "") or "").strip())
    out: list[dict[str, Any]] = []

    # --- Phase 1: version-specific matching ---
    versioned = _extract_versioned_techs(whatweb_lines)
    for i, item in enumerate(versioned[:3]):
        if i > 0 and not has_key:
            await asyncio.sleep(6.5)
        matches = await _nvd_versioned_search(
            item["tech"], item["version"], item["label"], settings
        )
        if not matches:
            continue
        cve_lines: list[str] = []
        max_cvss: float = 0.0
        fix_versions: list[str] = []
        for m in matches:
            score_str = f" (CVSS {m['cvss_score']:.1f})" if m["cvss_score"] else ""
            cve_lines.append(f"{m['cve_id']}{score_str}")
            if m["cvss_score"] and m["cvss_score"] > max_cvss:
                max_cvss = m["cvss_score"]
            if m["fix_version"] and m["fix_version"] not in fix_versions:
                fix_versions.append(m["fix_version"])

        if max_cvss >= 9.0:
            sev = "critical"
        elif max_cvss >= 7.0:
            sev = "high"
        elif max_cvss >= 4.0:
            sev = "medium"
        else:
            sev = "low"

        fix_note = (
            f" Upgrade to {' or '.join(fix_versions)} to remediate."
            if fix_versions else ""
        )
        out.append({
            "id": str(uuid.uuid4()),
            "severity": sev,
            "category": "Supply chain",
            "title": f"CVE match: {item['label']} {item['version']}",
            "description": (
                f"Detected **{item['label']} {item['version']}** on `{domain}`. "
                f"{len(matches)} CVE(s) affect this exact version."
                f"{fix_note}"
            ),
            "technical_detail": "; ".join(cve_lines),
            "affected_asset": domain,
            "remediation": (
                f"Upgrade {item['label']} from {item['version']}"
                + (f" to {fix_versions[0]}" if fix_versions else "")
                + "; review each CVE for applicability."
            ),
            "layer": "nvd_supply_chain",
            "compliance": ["Vendor patch management"],
        })

    if out:
        return out

    # --- Phase 2: fallback keyword search (original behaviour) ---
    kws = _extract_keywords(whatweb_lines)
    if not kws:
        return []

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
        out.append({
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
        })
    return out
