"""GitHub code search — heuristic for leaked secrets referencing the domain."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def search_domain(domain: str, token: str) -> dict[str, Any]:
    if not token:
        return {"layer": "github", "skipped": True, "reason": "no GITHUB_TOKEN"}
    q = f'"{domain}" (password OR secret OR api_key) in:file'
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = "https://api.github.com/search/code"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers, params={"q": q, "per_page": 5})
    if r.status_code == 403:
        return {"layer": "github", "error": "rate_limit_or_scope", "note": "Fine-grained token needs read access to code search"}
    if r.status_code != 200:
        return {"layer": "github", "error": f"http_{r.status_code}", "body": r.text[:500]}
    data = r.json()
    total = int(data.get("total_count") or 0)
    items = data.get("items") or []
    return {
        "layer": "github",
        "total_count": total,
        "sample_repos": [i.get("repository", {}).get("full_name") for i in items[:5]],
    }


def findings_from_github(domain: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    if summary.get("skipped") or summary.get("error"):
        return []
    total = int(summary.get("total_count") or 0)
    if total <= 0:
        return []
    return [
        {
            "id": str(uuid.uuid4()),
            "severity": "high" if total > 5 else "medium",
            "category": "Secrets exposure",
            "title": "Public GitHub code references this domain with secret-like context",
            "description": f"GitHub code search returned ~{total} hits (heuristic). Manual review required.",
            "technical_detail": str(summary.get("sample_repos", [])),
            "affected_asset": domain,
            "remediation": "Rotate any exposed credentials; remove secrets from history with secret scanning.",
            "layer": "github_search",
        }
    ]
