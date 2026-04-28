"""Ransomware Targeting Intelligence.

Cross-references the prospect's industry vertical and state/province against
active ransomware campaigns from ransomware.live.  Surfaces which active
threat groups have targeted their vertical in their geography in the last
90 days, and whether specific vulnerabilities found match known initial
access vectors used by those groups.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RANSOMWARE_LIVE_VICTIMS = "https://api.ransomware.live/victims"
RANSOMWARE_LIVE_GROUPS = "https://api.ransomware.live/groups"

# Common initial access vectors mapped to finding signals
_INITIAL_ACCESS_VECTORS: dict[str, list[str]] = {
    "phishing": ["spf", "dmarc", "dkim", "email"],
    "rdp_exposure": ["rdp", "3389", "remote desktop"],
    "vpn_exploit": ["vpn", "fortinet", "palo alto", "pulse secure", "citrix"],
    "web_exploit": ["cve", "nuclei", "vulnerability", "wordpress", "apache"],
    "credential_theft": ["breach", "stealer", "credential", "password"],
    "no_mfa": ["mfa", "no mfa", "multi-factor"],
}

# Map ransomware groups to their known preferred initial access
_GROUP_VECTORS: dict[str, list[str]] = {
    "lockbit": ["rdp_exposure", "vpn_exploit", "phishing", "credential_theft"],
    "blackcat": ["vpn_exploit", "credential_theft", "web_exploit"],
    "alphv": ["vpn_exploit", "credential_theft", "web_exploit"],
    "cl0p": ["web_exploit", "credential_theft"],
    "clop": ["web_exploit", "credential_theft"],
    "royal": ["phishing", "rdp_exposure", "credential_theft"],
    "blackbasta": ["phishing", "rdp_exposure", "no_mfa"],
    "black basta": ["phishing", "rdp_exposure", "no_mfa"],
    "akira": ["vpn_exploit", "credential_theft", "rdp_exposure"],
    "play": ["rdp_exposure", "vpn_exploit"],
    "medusa": ["rdp_exposure", "phishing", "credential_theft"],
    "bianlian": ["rdp_exposure", "vpn_exploit"],
    "rhysida": ["phishing", "vpn_exploit"],
    "hunters international": ["phishing", "rdp_exposure"],
    "8base": ["phishing", "credential_theft"],
    "ransomhub": ["vpn_exploit", "rdp_exposure", "phishing"],
}

# Industry vertical normalization
_INDUSTRY_ALIASES: dict[str, list[str]] = {
    "healthcare": ["health", "medical", "hospital", "clinic", "dental", "dentist", "orthodont", "pharma", "hipaa"],
    "legal": ["law", "legal", "attorney", "law firm"],
    "financial": ["bank", "financial", "credit union", "wealth", "investment", "accounting", "cpa"],
    "technology": ["tech", "software", "it ", "saas", "cloud"],
    "manufacturing": ["manufactur", "industrial"],
    "retail": ["retail", "ecommerce", "e-commerce", "shop"],
    "education": ["education", "school", "university", "college"],
    "government": ["government", "municipal", "federal", "state agency"],
}


def _normalize_industry(industry: str | None) -> str | None:
    if not industry:
        return None
    low = industry.lower().strip()
    for canonical, aliases in _INDUSTRY_ALIASES.items():
        if any(a in low for a in aliases):
            return canonical
    return low


def _normalize_state(state: str | None) -> str | None:
    if not state:
        return None
    return state.strip().lower()


async def _fetch_recent_victims(days: int = 90) -> list[dict[str, Any]]:
    """Fetch recent ransomware victims from ransomware.live API."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(RANSOMWARE_LIVE_VICTIMS)
            if r.status_code != 200:
                logger.warning("ransomware.live victims returned %d", r.status_code)
                return []
            victims = r.json()
    except Exception as e:
        logger.warning("ransomware.live fetch failed: %s", e)
        return []

    if not isinstance(victims, list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent: list[dict[str, Any]] = []
    for v in victims:
        date_str = v.get("published") or v.get("discovered") or v.get("date") or ""
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if dt >= cutoff:
            recent.append(v)

    return recent


def _match_victims(
    victims: list[dict[str, Any]],
    industry: str | None,
    state: str | None,
) -> list[dict[str, Any]]:
    """Filter victims matching the prospect's industry and optionally state."""
    norm_industry = _normalize_industry(industry)
    if not norm_industry:
        return []

    matched: list[dict[str, Any]] = []
    for v in victims:
        v_industry = _normalize_industry(
            v.get("activity") or v.get("sector") or v.get("industry") or ""
        )
        if v_industry != norm_industry:
            continue
        if state:
            v_country = (v.get("country") or "").lower()
            v_state = (v.get("state") or v.get("province") or "").lower()
            norm_st = _normalize_state(state)
            if norm_st and norm_st not in v_country and norm_st not in v_state:
                continue
        matched.append(v)

    return matched


def _find_vector_overlaps(
    group_name: str,
    findings: list[dict[str, Any]],
) -> list[str]:
    """Check if the prospect's vulnerabilities match the group's known initial access vectors."""
    group_key = group_name.lower().strip()
    vectors = _GROUP_VECTORS.get(group_key, [])
    if not vectors:
        for known_group, known_vectors in _GROUP_VECTORS.items():
            if known_group in group_key or group_key in known_group:
                vectors = known_vectors
                break
    if not vectors:
        return []

    findings_blob = " ".join(
        f"{f.get('title', '')} {f.get('category', '')} {f.get('description', '')} {f.get('technical_detail', '')}"
        for f in findings
    ).lower()

    overlapping: list[str] = []
    for vector in vectors:
        keywords = _INITIAL_ACCESS_VECTORS.get(vector, [])
        if any(kw in findings_blob for kw in keywords):
            overlapping.append(vector.replace("_", " ").title())

    return overlapping


async def ransomware_targeting_findings(
    domain: str,
    industry: str | None,
    state: str | None,
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Produce ransomware targeting intelligence findings."""
    if not industry:
        return []

    victims = await _fetch_recent_victims(days=90)
    if not victims:
        return []

    matched = _match_victims(victims, industry, state)
    if not matched:
        return []

    # Group by ransomware group
    groups: dict[str, list[dict[str, Any]]] = {}
    for v in matched:
        grp = (v.get("group_name") or v.get("group") or "Unknown").strip()
        groups.setdefault(grp, []).append(v)

    sorted_groups = sorted(groups.items(), key=lambda x: -len(x[1]))[:5]

    result_findings: list[dict[str, Any]] = []

    threat_lines: list[str] = []
    vector_warnings: list[str] = []

    for grp_name, grp_victims in sorted_groups:
        count = len(grp_victims)
        threat_lines.append(f"**{grp_name}**: {count} attack(s) on {_normalize_industry(industry)} targets")
        overlaps = _find_vector_overlaps(grp_name, findings)
        if overlaps:
            vector_warnings.append(
                f"{grp_name} uses {', '.join(overlaps)} — vulnerabilities matching these vectors were found on your domain"
            )

    sev = "critical" if vector_warnings else "high"

    desc = (
        f"In the last 90 days, {len(matched)} ransomware attack(s) targeted the "
        f"**{_normalize_industry(industry)}** vertical"
        + (f" in **{state}**" if state else "")
        + ". Active threat groups:\n\n"
        + "\n".join(f"- {line}" for line in threat_lines)
    )

    if vector_warnings:
        desc += (
            "\n\n**Your domain has vulnerabilities matching known initial access vectors:**\n\n"
            + "\n".join(f"- {w}" for w in vector_warnings)
        )

    remediation_parts = [
        "Prioritize patching vulnerabilities that match active ransomware initial access vectors.",
        "Enforce MFA on all portals.",
        "Restrict RDP and remote access to VPN-only.",
        "Implement offline backups and test restoration procedures.",
        "Review incident response plan against these specific threat groups.",
    ]

    result_findings.append({
        "id": str(uuid.uuid4()),
        "severity": sev,
        "category": "Ransomware intelligence",
        "title": f"Active ransomware campaigns targeting {_normalize_industry(industry)}",
        "description": desc,
        "technical_detail": "; ".join(vector_warnings) if vector_warnings else "No direct vector overlap detected",
        "affected_asset": domain,
        "remediation": " ".join(remediation_parts),
        "layer": "ransomware_intel",
        "compliance": [
            "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
            "45 CFR §164.308(a)(7)(i) — Contingency Plan",
        ],
    })

    return result_findings
