"""Orchestrate layers with parallelism (target 3–5 min wall clock)."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.analysis import email_security, ssl_deep
from app.breach_cost import build_estimate
from app.integrations import attack_paths, breach_monitoring, claude_interpret, exposure_screenshot, github_search, internetdb, nvd_cves
from app.models import Finding, ScanResponse
from app.pipeline.layers import dnstwist, httpx_whatweb, naabu, nuclei, subfinder
from app.scoring import compute_score
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_domain(domain: str) -> str:
    d = domain.lower().strip()
    if d.startswith("http://") or d.startswith("https://"):
        d = d.split("//", 1)[1].split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def _urls_from_naabu(naabu_results: list[dict]) -> list[str]:
    urls: list[str] = []
    for row in naabu_results:
        h = (row.get("host") or "").strip()
        p = (row.get("port") or "").strip()
        if not h:
            continue
        if p in ("", "443"):
            urls.append(f"https://{h}")
        elif p == "80":
            urls.append(f"http://{h}")
        elif p in ("8443", "4443"):
            urls.append(f"https://{h}:{p}")
        else:
            urls.append(f"http://{h}:{p}")
    return list(dict.fromkeys(urls))[:80]


def _merge_interpretations(findings: list[dict], interpreted: list[dict]) -> None:
    by_id = {str(x.get("id")): x for x in interpreted if x.get("id")}
    for f in findings:
        iid = str(f.get("id", ""))
        if iid and iid in by_id:
            f["interpretation"] = by_id[iid].get("plain_english")
            f["fix_guide"] = by_id[iid].get("fix_guide")


def _dnstwist_findings(domain: str, data: dict) -> list[dict[str, Any]]:
    reg = data.get("registered") or []
    if not reg:
        return []
    return [
        {
            "id": str(uuid.uuid4()),
            "severity": "medium",
            "category": "Lookalike domains",
            "title": "Registered lookalike domains detected",
            "description": f"dnstwist reported {len(reg)} registered permutation(s). Review typosquat risk.",
            "technical_detail": str(reg[:20])[:4000],
            "affected_asset": domain,
            "remediation": "Register defensive domains, monitor brand abuse, and warn users.",
            "layer": "dnstwist",
        }
    ]


async def run_scan(
    domain: str,
    *,
    scan_id: str | None = None,
    industry: str | None = None,
    company_name: str | None = None,
    settings: Settings | None = None,
) -> ScanResponse:
    settings = settings or get_settings()
    domain = _normalize_domain(domain)
    started = _iso_now()
    raw_layers: dict[str, Any] = {}

    l1 = await subfinder.run(domain, settings)
    raw_layers["subfinder"] = l1
    hosts = list(dict.fromkeys([domain] + l1.get("hosts", [])))

    l2_task = naabu.run(hosts, settings)
    l5_task = dnstwist.run(domain, settings)
    l7_task = email_security.analyze(domain)
    l8_task = ssl_deep.analyze(domain)
    l6_task = breach_monitoring.run_breach_layers(domain, settings)
    l9_task = github_search.search_domain(domain, settings.github_token)

    l2, l5, l7, l8, breach_summaries, gh_sum = await asyncio.gather(
        l2_task, l5_task, l7_task, l8_task, l6_task, l9_task
    )
    raw_layers["naabu"] = l2
    raw_layers["dnstwist"] = l5
    raw_layers["breach_monitoring"] = breach_summaries
    raw_layers["github"] = gh_sum

    all_findings: list[dict[str, Any]] = []
    all_findings.extend(l7)
    all_findings.extend(l8)
    all_findings.extend(
        breach_monitoring.build_breach_monitoring_findings(
            domain, breach_summaries, company_name=company_name
        )
    )
    all_findings.extend(github_search.findings_from_github(domain, gh_sum))
    all_findings.extend(_dnstwist_findings(domain, l5))

    naabu_results = l2.get("results") or []
    targets = _urls_from_naabu(naabu_results)
    if not targets:
        targets = [f"https://{domain}", f"http://{domain}"]

    try:
        idb_fs = await internetdb.internetdb_findings(naabu_results, domain)
        all_findings.extend(idb_fs)
        raw_layers["internetdb_findings"] = len(idb_fs)
    except Exception:
        logger.exception("InternetDB layer failed")
        raw_layers["internetdb_findings"] = 0

    l3a_task = httpx_whatweb.run_httpx(targets, settings)
    l3b_task = httpx_whatweb.run_whatweb([u for u in targets[:15]], settings)
    l3a, l3b = await asyncio.gather(l3a_task, l3b_task)
    raw_layers["httpx"] = l3a
    raw_layers["whatweb"] = l3b

    try:
        nvd_fs = await nvd_cves.nvd_findings_from_whatweb(
            l3b.get("lines") or [],
            domain,
            settings,
        )
        all_findings.extend(nvd_fs)
        raw_layers["nvd_supply_chain_findings"] = len(nvd_fs)
    except Exception:
        logger.exception("NVD supply-chain layer failed")
        raw_layers["nvd_supply_chain_findings"] = 0

    try:
        shot_fs = await exposure_screenshot.capture_exposure_screenshots(
            l3a.get("jsonl") or [],
            domain,
        )
        all_findings.extend(shot_fs)
        raw_layers["exposure_screenshots"] = len(shot_fs)
    except Exception:
        logger.exception("exposure screenshots failed")
        raw_layers["exposure_screenshots"] = 0

    httpx_urls: list[str] = []
    for row in l3a.get("jsonl") or []:
        u = row.get("url") or row.get("final_url")
        if u:
            httpx_urls.append(u)
    httpx_urls = list(dict.fromkeys(httpx_urls))[:30]
    if not httpx_urls:
        httpx_urls = targets[:10]

    l4_meta, nuc_findings = await nuclei.run(httpx_urls, domain, settings)
    raw_layers["nuclei"] = l4_meta
    all_findings.extend(nuc_findings)

    interpreted = await claude_interpret.interpret_findings(all_findings, settings)
    raw_layers["interpreted_count"] = len(interpreted)
    _merge_interpretations(all_findings, interpreted)

    paths = await attack_paths.compute_attack_paths(
        domain=domain,
        industry=industry,
        company_name=company_name,
        findings=all_findings,
        settings=settings,
    )
    raw_layers["attack_paths_count"] = len(paths)

    score, grade, mult = compute_score(all_findings, industry)
    crit = sum(1 for f in all_findings if (f.get("severity") or "").lower() == "critical")
    breach_est = build_estimate(industry, len(all_findings), crit)

    completed = _iso_now()
    findings_models = [Finding.model_validate(f) for f in all_findings]

    return ScanResponse(
        scan_id=scan_id,
        domain=domain,
        status="completed",
        score=score,
        grade=grade,
        findings=findings_models,
        started_at=started,
        completed_at=completed,
        scan_version="2.0",
        industry=industry,
        industry_risk_multiplier=mult,
        raw_layers=raw_layers,
        interpreted_findings=interpreted,
        breach_cost_estimate=breach_est,
        attack_paths=paths,
    )


async def run_scan_fast(
    domain: str,
    *,
    scan_id: str | None = None,
    industry: str | None = None,
    company_name: str | None = None,
    settings: Settings | None = None,
) -> ScanResponse:
    """
    Tier 1 fast path for Charlotte: email auth + TLS + breach stack + subdomains only.
    Target ~10–20s wall clock (no nuclei/naabu/httpx/dnstwist/github/Claude interpret).
    """
    settings = settings or get_settings()
    domain = _normalize_domain(domain)
    started = _iso_now()
    raw_layers: dict[str, Any] = {}

    l_sub = await subfinder.run(domain, settings)
    raw_layers["subfinder"] = l_sub
    hosts = list(dict.fromkeys([domain] + (l_sub.get("hosts") or [])))

    l7_task = email_security.analyze(domain)
    l8_task = ssl_deep.analyze(domain)
    l6_task = breach_monitoring.run_breach_layers(domain, settings)

    l7, l8, breach_summaries = await asyncio.gather(l7_task, l8_task, l6_task)
    raw_layers["breach_monitoring"] = breach_summaries

    all_findings: list[dict[str, Any]] = []
    all_findings.extend(l7)
    all_findings.extend(l8)
    all_findings.extend(
        breach_monitoring.build_breach_monitoring_findings(
            domain, breach_summaries, company_name=company_name
        )
    )
    if len(hosts) > 2:
        all_findings.append(
            {
                "id": str(uuid.uuid4()),
                "severity": "low",
                "category": "Attack surface",
                "title": "Subdomain footprint",
                "description": (
                    f"Quick pass found {len(hosts)} hostnames for this domain. "
                    "A wider footprint usually means more surface area — review anything you do not recognize."
                ),
                "technical_detail": str(hosts[:40])[:4000],
                "affected_asset": domain,
                "remediation": "Review DNS and retire unused hosts.",
                "layer": "subfinder",
            }
        )

    score, grade, mult = compute_score(all_findings, industry)
    crit = sum(1 for f in all_findings if (f.get("severity") or "").lower() == "critical")
    breach_est = build_estimate(industry, len(all_findings), crit)
    completed = _iso_now()
    findings_models = [Finding.model_validate(f) for f in all_findings]

    return ScanResponse(
        scan_id=scan_id,
        domain=domain,
        status="completed",
        score=score,
        grade=grade,
        findings=findings_models,
        started_at=started,
        completed_at=completed,
        scan_version="2.0-fast",
        industry=industry,
        industry_risk_multiplier=mult,
        raw_layers=raw_layers,
        interpreted_findings=[],
        breach_cost_estimate=breach_est,
        attack_paths=[],
    )


async def run_dnstwist_only(
    domain: str,
    *,
    scan_id: str | None = None,
    industry: str | None = None,
    company_name: str | None = None,
    settings: Settings | None = None,
) -> ScanResponse:
    """Lightweight job: dnstwist only (Shield daily lookalike pass)."""
    settings = settings or get_settings()
    domain = _normalize_domain(domain)
    started = _iso_now()
    l5 = await dnstwist.run(domain, settings)
    raw_layers: dict[str, Any] = {"dnstwist": l5}
    all_findings = _dnstwist_findings(domain, l5)
    score, grade, mult = compute_score(all_findings, industry)
    crit = sum(1 for f in all_findings if (f.get("severity") or "").lower() == "critical")
    breach_est = build_estimate(industry, len(all_findings), crit)
    completed = _iso_now()
    findings_models = [Finding.model_validate(f) for f in all_findings]
    return ScanResponse(
        scan_id=scan_id,
        domain=domain,
        status="completed",
        score=score,
        grade=grade,
        findings=findings_models,
        started_at=started,
        completed_at=completed,
        scan_version="2.0-dnstwist",
        industry=industry,
        industry_risk_multiplier=mult,
        raw_layers=raw_layers,
        interpreted_findings=[],
        breach_cost_estimate=breach_est,
        attack_paths=[],
    )
