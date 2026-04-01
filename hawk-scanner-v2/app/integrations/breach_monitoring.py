"""
Multi-source breach / stealer monitoring (replaces sole reliance on Breachsense).

Layers:
  F — Breachsense (optional; highest priority when configured)
  A — Hudson Rock Cavalier (free, no key)
  D — ransomware.live API via search (needs RANSOMWATCH_API_TOKEN)
  B — DeHashed (Basic auth)
  C — OathNet (Bearer)
  E — HIBP domain breached accounts (existing API)

Findings use layer=breach_monitoring and breach_source for traceability.
Priority order (for sorting): breachsense > hudson_rock > ransomwatch > dehashed > oathnet > hibp_domain
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from typing import Any

import httpx

from app.integrations import breachsense, hibp_domain
from app.settings import Settings

logger = logging.getLogger(__name__)

HUDSON_ROCK_URL = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-domain"
DEHASHED_SEARCH_URL = "https://api.dehashed.com/search"
OATHNET_SEARCH_URL = "https://api.oathnet.org/v1/search"
RANSOMWARE_LIVE_SEARCH = "https://api-pro.ransomware.live/victims/search"

# Sort order: lower = higher priority in combined breach block
BREACH_SOURCE_PRIORITY: dict[str, int] = {
    "breachsense": 0,
    "hudson_rock": 1,
    "ransomwatch": 2,
    "dehashed": 3,
    "oathnet": 4,
    "hibp_domain": 5,
}

_HASHY_PASSWORD = re.compile(r"^(\$2[aby]\$|\$argon2|\*[0-9a-f]{32}\*|^[a-f0-9]{32}$|^[a-f0-9]{40}$)", re.I)


def _bfinding(
    *,
    severity: str,
    title: str,
    description: str,
    remediation: str,
    domain: str,
    breach_source: str,
    technical_detail: str = "",
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "severity": severity,
        "category": "Breach monitoring",
        "title": title,
        "description": description,
        "technical_detail": (technical_detail or "")[:4000],
        "affected_asset": domain,
        "remediation": remediation,
        "layer": "breach_monitoring",
        "breach_source": breach_source,
    }


def _hudson_stealer_count(data: Any) -> int:
    """Best-effort count of stealer-related rows from Hudson Rock JSON."""
    if not isinstance(data, dict):
        return 0
    if data.get("error"):
        return 0

    for key in ("stealers", "stealerLogs", "stealer_logs", "stealerData", "results", "records", "data"):
        chunk = data.get(key)
        if isinstance(chunk, list) and chunk:
            return len(chunk)
        if isinstance(chunk, dict):
            inner = chunk.get("stealers") or chunk.get("logs") or chunk.get("items")
            if isinstance(inner, list) and inner:
                return len(inner)

    for path in (
        ("statistics", "totalStealers"),
        ("statistics", "stealersCount"),
        ("overview", "compromisedEmployees"),
        ("totalStealers",),
        ("stealerCount",),
        ("compromisedCount",),
    ):
        cur: Any = data
        ok = True
        for p in path:
            if not isinstance(cur, dict):
                ok = False
                break
            cur = cur.get(p)
        if ok and isinstance(cur, int) and cur > 0:
            return cur

    # Deep scan: any list whose key mentions stealer
    for k, v in data.items():
        if isinstance(v, list) and v and "stealer" in str(k).lower():
            return len(v)
    return 0


def _dehashed_plaintext_hits(entries: list[Any]) -> int:
    n = 0
    for row in entries:
        if not isinstance(row, dict):
            continue
        pwd = row.get("password") or row.get("plaintext_password") or row.get("clear_text_password")
        if not pwd or not isinstance(pwd, str):
            continue
        p = pwd.strip()
        if len(p) < 3:
            continue
        if _HASHY_PASSWORD.match(p):
            continue
        if len(p) >= 60 and not p.isprintable():
            continue
        n += 1
    return n


async def _fetch_hudson(domain: str, timeout: float = 50.0) -> dict[str, Any]:
    url = HUDSON_ROCK_URL
    params = {"domain": domain.lower().strip()}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, params=params)
    except Exception as e:
        logger.warning("hudson rock request failed: %s", e)
        return {"layer": "hudson_rock", "error": str(e)[:200]}
    if r.status_code >= 400:
        return {"layer": "hudson_rock", "error": f"http_{r.status_code}", "preview": r.text[:300]}
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:2000]}
    return {"layer": "hudson_rock", "data": data, "stealer_count": _hudson_stealer_count(data)}


async def _fetch_dehashed(domain: str, email: str, api_key: str, timeout: float = 45.0) -> dict[str, Any]:
    if not email or not api_key:
        return {"layer": "dehashed", "skipped": True, "reason": "no DEHASHED_EMAIL / DEHASHED_API_KEY"}
    auth = base64.b64encode(f"{email.strip()}:{api_key.strip()}".encode()).decode()
    headers = {"Accept": "application/json", "Authorization": f"Basic {auth}"}
    params = {"query": f"domain:{domain.lower().strip()}", "size": "100"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(DEHASHED_SEARCH_URL, headers=headers, params=params)
    except Exception as e:
        logger.warning("dehashed request failed: %s", e)
        return {"layer": "dehashed", "error": str(e)[:200]}
    if r.status_code == 401:
        return {"layer": "dehashed", "error": "invalid_credentials"}
    if r.status_code >= 400:
        return {"layer": "dehashed", "error": f"http_{r.status_code}", "preview": r.text[:300]}
    try:
        data = r.json()
    except Exception:
        return {"layer": "dehashed", "error": "invalid_json", "preview": r.text[:400]}
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        entries = []
    plain_n = _dehashed_plaintext_hits(entries)
    return {
        "layer": "dehashed",
        "entry_count": len(entries),
        "plaintext_password_hits": plain_n,
        "pii_redacted": True,
    }


async def _fetch_oathnet(domain: str, api_key: str, timeout: float = 45.0) -> dict[str, Any]:
    if not api_key:
        return {"layer": "oathnet", "skipped": True, "reason": "no OATHNET_API_KEY"}
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key.strip()}"}
    params = {"domain": domain.lower().strip()}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(OATHNET_SEARCH_URL, headers=headers, params=params)
    except Exception as e:
        logger.warning("oathnet request failed: %s", e)
        return {"layer": "oathnet", "error": str(e)[:200]}
    if r.status_code >= 400:
        return {"layer": "oathnet", "error": f"http_{r.status_code}", "preview": r.text[:300]}
    try:
        data = r.json()
    except Exception:
        data = {}
    hits = 0
    if isinstance(data, dict):
        for key in ("results", "data", "hits", "records", "items", "leaks"):
            chunk = data.get(key)
            if isinstance(chunk, list):
                hits = max(hits, len(chunk))
        if hits == 0 and isinstance(data.get("count"), int):
            hits = int(data["count"])
    elif isinstance(data, list):
        hits = len(data)
    return {"layer": "oathnet", "hit_count": hits, "pii_redacted": True}


async def _fetch_ransomwatch_search(domain: str, token: str, timeout: float = 45.0) -> dict[str, Any]:
    if not token:
        return {"layer": "ransomwatch", "skipped": True, "reason": "no RANSOMWATCH_API_TOKEN"}
    headers = {
        "Accept": "application/json",
        "User-Agent": "HAWK-Scanner-2/1.0",
        "X-API-KEY": token.strip(),
    }
    params = {"q": domain.lower().strip()}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(RANSOMWARE_LIVE_SEARCH, headers=headers, params=params)
    except Exception as e:
        logger.warning("ransomware.live search failed: %s", e)
        return {"layer": "ransomwatch", "error": str(e)[:200]}
    if r.status_code == 401:
        return {"layer": "ransomwatch", "error": "invalid_token"}
    if r.status_code >= 400:
        return {"layer": "ransomwatch", "error": f"http_{r.status_code}", "preview": r.text[:300]}
    try:
        data = r.json()
    except Exception:
        return {"layer": "ransomwatch", "error": "invalid_json"}
    victims = data.get("victims") if isinstance(data, dict) else None
    if not isinstance(victims, list):
        victims = data if isinstance(data, list) else []
    dom = domain.lower().strip()
    matched = False
    sample: list[str] = []
    for v in victims[:50]:
        blob = json.dumps(v, default=str).lower() if isinstance(v, (dict, list)) else str(v).lower()
        if dom in blob or dom.replace("www.", "") in blob:
            matched = True
            if isinstance(v, dict):
                name = str(v.get("victim") or v.get("company") or v.get("name") or "")[:120]
                if name:
                    sample.append(name)
            if len(sample) >= 3:
                break
    return {
        "layer": "ransomwatch",
        "victim_match": matched,
        "search_result_count": len(victims),
        "sample_names_redacted": sample,
    }


def _findings_hudson(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    if summary.get("error") and "data" not in summary:
        return []
    n = int(summary.get("stealer_count") or 0)
    if n <= 0:
        return []
    return [
        _bfinding(
            severity="critical",
            title="Employee credentials stolen by active malware.",
            description=(
                f"Hudson Rock infostealer intelligence reports {n} stealer-related record(s) tied to "
                f"your domain. That usually means malware on a device exfiltrated passwords or session data."
            ),
            remediation=(
                "Reset passwords for affected users, enforce MFA everywhere, isolate and scan impacted devices, "
                "and review endpoint detection. Treat sessions as compromised until rotated."
            ),
            domain=domain,
            breach_source="hudson_rock",
            technical_detail=json.dumps(summary.get("data"), default=str)[:3500] if summary.get("data") else "",
        )
    ]


def _findings_dehashed(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    if summary.get("skipped") or summary.get("error"):
        return []
    n = int(summary.get("plaintext_password_hits") or 0)
    if n <= 0:
        return []
    return [
        _bfinding(
            severity="high",
            title="Employee passwords exposed in data breach.",
            description=(
                f"DeHashed returned {n} record(s) for your domain with recoverable or plaintext-style passwords. "
                "These often come from third-party breaches or paste sites."
            ),
            remediation=(
                "Force password resets, ban password reuse, enable MFA, and check for unauthorized logins. "
                "Consider a dark-web monitoring policy for executive accounts."
            ),
            domain=domain,
            breach_source="dehashed",
            technical_detail=f"entry_count={summary.get('entry_count')}, plaintext_hits={n} (values redacted)",
        )
    ]


def _findings_oathnet(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    if summary.get("skipped") or summary.get("error"):
        return []
    hits = int(summary.get("hit_count") or 0)
    if hits <= 0:
        return []
    return [
        _bfinding(
            severity="medium",
            title="Dark web or stealer exposure reported for your domain.",
            description=(
                f"OathNet reported {hits} relevant hit(s) for your domain across stealer logs and related sources "
                "(details withheld)."
            ),
            remediation=(
                "Validate critical accounts, rotate credentials where appropriate, and tighten endpoint and email security."
            ),
            domain=domain,
            breach_source="oathnet",
            technical_detail=f"hit_count={hits}",
        )
    ]


def _findings_ransomwatch(domain: str, company_name: str | None, summary: dict[str, Any]) -> list[dict[str, Any]]:
    if summary.get("skipped") or summary.get("error"):
        return []
    if not summary.get("victim_match"):
        return []
    who = (company_name or domain).strip()
    return [
        _bfinding(
            severity="critical",
            title=f"{who} appears on ransomware gang leak site.",
            description=(
                "ransomware.live victim intelligence matched your domain to a published leak or victim listing. "
                "This may indicate a past or claimed ransomware incident; verify with internal IT and backups."
            ),
            remediation=(
                "Invoke incident response: preserve logs, validate backup integrity, engage counsel and insurers, "
                "and do not pay ransoms without a formal decision process."
            ),
            domain=domain,
            breach_source="ransomwatch",
            technical_detail=json.dumps(
                {"sample_hints": summary.get("sample_names_redacted"), "results": summary.get("search_result_count")},
                default=str,
            )[:2000],
        )
    ]


def _findings_hibp_breach_block(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    """HIBP as layer E — always medium severity in this block (per product priority)."""
    if summary.get("skipped") or summary.get("error"):
        return []
    n = int(summary.get("exposed_accounts") or 0)
    if n <= 0:
        return []
    return [
        _bfinding(
            severity="medium",
            title="Domain emails appeared in known public breaches.",
            description=(
                f"Have I Been Pwned reports {n} address(es) on this domain in historical breaches (addresses not stored)."
            ),
            remediation="Force password resets where reused passwords are suspected, enforce MFA, and monitor for abuse.",
            domain=domain,
            breach_source="hibp_domain",
            technical_detail="Have I Been Pwned breached domain search",
        )
    ]


def _breachsense_to_breach_monitoring_findings(domain: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in findings:
        nf = dict(f)
        nf["layer"] = "breach_monitoring"
        nf["breach_source"] = "breachsense"
        nf["category"] = "Breach monitoring"
        out.append(nf)
    return out


def _sort_breach_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda x: BREACH_SOURCE_PRIORITY.get(str(x.get("breach_source") or ""), 99),
    )


async def run_breach_layers(domain: str, settings: Settings) -> dict[str, Any]:
    """Run A–E and Breachsense (F) in parallel; return raw summaries only."""
    d = domain.lower().strip()

    hudson_t = _fetch_hudson(d)
    dehashed_t = _fetch_dehashed(d, settings.dehashed_email, settings.dehashed_api_key)
    oathnet_t = _fetch_oathnet(d, settings.oathnet_api_key)
    ransom_t = _fetch_ransomwatch_search(d, settings.ransomwatch_api_token)
    hibp_t = hibp_domain.check_domain(d, settings.hibp_api_key)
    sense_t = breachsense.check_domain(d, settings.breachsense_api_key, settings.breachsense_base_url)

    hudson, dehashed, oathnet, ransom, hibp_sum, sense_sum = await asyncio.gather(
        hudson_t, dehashed_t, oathnet_t, ransom_t, hibp_t, sense_t
    )

    return {
        "hudson_rock": hudson,
        "dehashed": dehashed,
        "oathnet": oathnet,
        "ransomwatch": ransom,
        "hibp_domain": hibp_sum,
        "breachsense": sense_sum,
    }


def build_breach_monitoring_findings(
    domain: str,
    summaries: dict[str, Any],
    *,
    company_name: str | None = None,
) -> list[dict[str, Any]]:
    """Turn layer summaries into sorted findings (F > A > D > B > C > E)."""
    findings: list[dict[str, Any]] = []

    # F — Breachsense (highest priority when active)
    sense_raw = breachsense.findings_from_breachsense(domain, summaries.get("breachsense") or {})
    findings.extend(_breachsense_to_breach_monitoring_findings(domain, sense_raw))

    findings.extend(_findings_hudson(domain, summaries.get("hudson_rock") or {}))
    findings.extend(_findings_ransomwatch(domain, company_name, summaries.get("ransomwatch") or {}))
    findings.extend(_findings_dehashed(domain, summaries.get("dehashed") or {}))
    findings.extend(_findings_oathnet(domain, summaries.get("oathnet") or {}))
    findings.extend(_findings_hibp_breach_block(domain, summaries.get("hibp_domain") or {}))

    return _sort_breach_findings(findings)
