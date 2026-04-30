"""Version-aware NVD CVE matching from WhatWeb fingerprints.

Extracts technology **name + version** from WhatWeb output, queries NVD for
that specific product, and keeps only the CVEs whose CPE version range covers
the detected version. Every finding includes the exact version detected, the
top CVE (highest CVSS), its score, and the best patched version — rendered in
the spec format::

    WordPress 6.4.1 — CVE-2024-4439, CVSS 8.8, patch to 6.5.3

When a technology is visible but no version can be extracted, the fallback
layer emits a low-severity informational hint ("version unknown — verify
vendor advisories") rather than a generic "known CVEs" statement, so clients
never see the vague ``"<tech> has known CVEs"`` output.
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
    """Parse '2.4.51' → (2, 4, 51). Non-numeric components stop parsing."""
    parts: list[int] = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def _max_version(versions: list[str]) -> str | None:
    """Pick the semantically largest version string from a list.

    Used to collapse multiple ``versionEndExcluding`` values into a single
    "upgrade to X" target that clears every matching CVE at once.
    """
    if not versions:
        return None
    return max(versions, key=_parse_version_tuple)


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


def _versioned_techs_from_keywords(
    lines: list[str], versioned: list[dict[str, str]]
) -> list[str]:
    """Return tech keywords visible in fingerprint that have *no* version."""
    have_version = {v["tech"] for v in versioned}
    out: list[str] = []
    for kw in _extract_keywords(lines):
        tech = kw.lower().replace(" ", "-")
        if tech not in have_version and kw not in out:
            out.append(kw)
    return out


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


def _severity_from_cvss(score: float | None) -> str:
    if score is None:
        return "medium"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


async def _nvd_versioned_search(
    tech: str,
    version: str,
    label: str,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Query NVD for *tech* and keep CVEs whose CPE range covers *version*.

    Each returned dict has ``cve_id``, ``cvss_score`` (float | None),
    ``cvss_vector`` (str), and ``fix_version`` (str | None). Sorted by CVSS
    descending so callers can take the first entry as the headline CVE.
    """
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
    tech_norm = tech.lower().replace("-", "").replace("_", "")
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
                    if tech_norm not in cpe_uri.replace("-", "").replace("_", ""):
                        continue
                    si = cm.get("versionStartIncluding")
                    se = cm.get("versionStartExcluding")
                    ei = cm.get("versionEndIncluding")
                    ee = cm.get("versionEndExcluding")
                    if si or se or ei or ee:
                        if _version_in_range(version, si, se, ei, ee):
                            version_hit = True
                            if ee:
                                # Take the highest versionEndExcluding across
                                # matching ranges in this CVE. Multiple CPE
                                # match rows can cover the same detected
                                # version (e.g. ranges [6.0,6.5.3) and
                                # [6.0,6.8.0) both cover 6.4.1); upgrading
                                # to 6.5.3 would still leave the second range
                                # triggered. Only the max escapes every
                                # matching range for this CVE.
                                if not fix_ver or _parse_version_tuple(ee) > _parse_version_tuple(fix_ver):
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

    # Sort by CVSS desc (None treated as 0) so the top entry is the worst.
    matched.sort(key=lambda m: (m.get("cvss_score") or 0.0), reverse=True)
    return matched[:5]


def _build_versioned_finding(
    label: str,
    version: str,
    domain: str,
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render the spec-format finding for a tech/version with >=1 matched CVE."""
    top = matches[0]
    top_cve: str = top["cve_id"]
    top_cvss: float | None = top.get("cvss_score")

    fix_versions = [m["fix_version"] for m in matches if m.get("fix_version")]
    best_fix = _max_version(fix_versions)

    # Spec headline: "WordPress 6.4.1 — CVE-2024-4439, CVSS 8.8, patch to 6.5.3"
    cvss_phrase = f"CVSS {top_cvss:.1f}" if top_cvss is not None else "CVSS unknown"
    title_parts = [f"{label} {version} — {top_cve}, {cvss_phrase}"]
    if best_fix:
        title_parts.append(f"patch to {best_fix}")
    title = ", ".join(title_parts)

    # Per-CVE technical detail, one per line.
    detail_lines: list[str] = []
    for m in matches:
        score = m.get("cvss_score")
        score_part = f"CVSS {score:.1f}" if score is not None else "CVSS n/a"
        fix_part = f"patch to {m['fix_version']}" if m.get("fix_version") else "no patch listed"
        detail_lines.append(f"{m['cve_id']} — {score_part} — {fix_part}")
    technical_detail = "\n".join(detail_lines)

    description = (
        f"Detected **{label} {version}** on `{domain}`. "
        f"{len(matches)} CVE(s) affect this exact version; highest is "
        f"{top_cve} ({cvss_phrase})."
    )
    if best_fix:
        description += f" Upgrade to {best_fix} to clear every matched CVE."

    remediation = (
        f"Upgrade {label} from {version}"
        + (f" to {best_fix}" if best_fix else "")
        + f" to remediate {top_cve}"
        + (f" and {len(matches) - 1} other CVE(s)" if len(matches) > 1 else "")
        + "; verify in a staging environment before rolling out."
    )

    return {
        "id": str(uuid.uuid4()),
        "severity": _severity_from_cvss(top_cvss),
        "category": "Supply chain",
        "title": title,
        "description": description,
        "technical_detail": technical_detail,
        "affected_asset": domain,
        "remediation": remediation,
        "layer": "nvd_supply_chain",
        "compliance": ["Vendor patch management"],
    }


def _build_unknown_version_finding(
    kw: str, domain: str, cve_ids: list[str]
) -> dict[str, Any]:
    """Low-severity hint when fingerprint shows *kw* but no version.

    Avoids the vague "known CVEs" framing — explicitly says version detection
    is required before CVE matching can be authoritative.
    """
    sample = ", ".join(cve_ids[:3]) if cve_ids else "none in sample"
    return {
        "id": str(uuid.uuid4()),
        "severity": "info",
        "category": "Supply chain",
        "title": f"{kw} detected — version unknown; verify vendor advisories",
        "description": (
            f"WhatWeb fingerprinted **{kw}** on `{domain}` but did not expose a "
            "version string, so exact CVE matching is not possible. A sample "
            f"of recent NVD records for {kw}: {sample}. "
            "Run a version scan (or enable server version headers in a "
            "controlled window) and re-scan for authoritative CVE results."
        ),
        "technical_detail": ", ".join(cve_ids[:5]),
        "affected_asset": domain,
        "remediation": (
            f"Identify the installed {kw} version, compare against the latest "
            "vendor advisory, and patch if below the current supported release."
        ),
        "layer": "nvd_supply_chain",
        "compliance": ["Vendor patch management"],
    }


async def nvd_findings_from_whatweb(
    whatweb_lines: list[str],
    domain: str,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Version-aware NVD matching with informational fallback for unknowns."""
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
        out.append(_build_versioned_finding(item["label"], item["version"], domain, matches))

    # --- Phase 2: fallback — tech visible, no version extracted ---
    if os.environ.get("HAWK_NVD_KEYWORD_FALLBACK", "1").strip().lower() in ("0", "false", "no"):
        return out

    unknowns = _versioned_techs_from_keywords(whatweb_lines, versioned)
    for i, kw in enumerate(unknowns[:2]):
        if i > 0 and not has_key:
            await asyncio.sleep(6.5)
        cve_ids = await _nvd_keyword_search(kw, settings)
        if not cve_ids:
            continue
        out.append(_build_unknown_version_finding(kw, domain, cve_ids))

    return out
