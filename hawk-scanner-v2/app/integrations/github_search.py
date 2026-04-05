"""GitHub code search — leaked secrets / domain references (Phase 3)."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SEARCH_QUERIES: tuple[str, ...] = (
    '"{domain}" (password OR secret OR api_key OR token) in:file',
    '"{domain}" (sk_live OR AKIA OR AWS_SECRET OR BEGIN PRIVATE KEY) in:file',
)


async def search_domain(domain: str, token: str) -> dict[str, Any]:
    if not token:
        return {"layer": "github", "skipped": True, "reason": "no GITHUB_TOKEN"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = "https://api.github.com/search/code"
    counts: list[int] = []
    sample_repos: list[str] = []
    high_signal_paths: list[str] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=35.0) as client:
        for q_template in SEARCH_QUERIES:
            q = q_template.format(domain=domain)
            try:
                r = await client.get(url, headers=headers, params={"q": q, "per_page": 8})
            except Exception as e:
                errors.append(str(e)[:120])
                continue
            if r.status_code == 403:
                return {
                    "layer": "github",
                    "error": "rate_limit_or_scope",
                    "note": "Fine-grained token needs read access to code search",
                }
            if r.status_code != 200:
                errors.append(f"http_{r.status_code}")
                continue
            data = r.json()
            counts.append(int(data.get("total_count") or 0))
            items = data.get("items") or []
            for i in items[:8]:
                repo = i.get("repository", {}).get("full_name")
                if repo and repo not in sample_repos:
                    sample_repos.append(repo)
                path = str(i.get("path") or "")
                if any(x in path.lower() for x in (".env", "credentials", "secret", "id_rsa", "token")):
                    high_signal_paths.append(f"{repo}:{path}" if repo else path)

    total = max(counts) if counts else 0
    return {
        "layer": "github",
        "total_count": total,
        "sample_repos": sample_repos[:10],
        "high_signal_paths": high_signal_paths[:12],
        "query_errors": errors[:5],
    }


def findings_from_github(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    if summary.get("skipped") or summary.get("error"):
        return []
    total = int(summary.get("total_count") or 0)
    if total <= 0:
        return []
    high_paths = summary.get("high_signal_paths") or []
    criticalish = bool(high_paths) or total >= 3
    sev = "critical" if criticalish and total >= 1 else "high" if total > 8 else "medium"
    detail_bits = [str(summary.get("sample_repos", []))]
    if high_paths:
        detail_bits.append("high_signal:" + "; ".join(high_paths[:6]))
    return [
        {
            "id": str(uuid.uuid4()),
            "severity": sev,
            "category": "Secrets exposure",
            "title": "Public GitHub code may expose credentials tied to your domain",
            "description": (
                f"GitHub code search returned ~{total} hit(s) across heuristic secret-focused queries. "
                "Treat as sensitive until manually ruled out."
            ),
            "technical_detail": " ".join(detail_bits)[:8000],
            "affected_asset": domain,
            "remediation": (
                "Rotate any exposed credentials immediately; remove secrets from Git history (BFG/git filter-repo); "
                "enable GitHub secret scanning; use private repos for internal keys."
            ),
            "layer": "github_search",
        }
    ]
