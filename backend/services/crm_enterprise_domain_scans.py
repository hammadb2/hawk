"""Phase 4 — Enterprise monitored domains: fast rescans → client_domain_scans rollup."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from services.scanner import enqueue_async_scan, poll_scan_job

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _findings_json(result: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    raw = result.get("findings")
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for x in raw[:400]:
            if isinstance(x, dict):
                out.append(x)
            elif hasattr(x, "model_dump"):
                out.append(x.model_dump())
        return out
    if isinstance(raw, dict):
        inner = raw.get("findings")
        if isinstance(inner, list):
            return [x for x in inner[:400] if isinstance(x, dict)]
        return raw
    return []


def run_enterprise_domain_scans() -> dict[str, Any]:
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured", "scanned": 0}

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={
            "status": "eq.active",
            "select": "id,domain,company_name,prospect_id,monitored_domains,industry",
            "limit": "500",
        },
        timeout=60.0,
    )
    r.raise_for_status()
    rows: list[dict[str, Any]] = r.json() or []

    scanned = 0
    errors: list[str] = []

    for c in rows:
        extras = c.get("monitored_domains") or []
        if not extras or not isinstance(extras, list):
            continue
        cid = str(c["id"])
        primary = (c.get("domain") or "").strip().lower()
        company = (c.get("company_name") or primary or "Client").strip()
        pid = c.get("prospect_id")
        industry = None
        if pid:
            pr = httpx.get(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_headers(),
                params={"id": f"eq.{pid}", "select": "industry", "limit": "1"},
                timeout=15.0,
            )
            if pr.status_code == 200 and pr.json():
                industry = (pr.json()[0] or {}).get("industry")

        doms: list[str] = []
        if primary:
            doms.append(primary)
        for x in extras:
            d = str(x).strip().lower()
            if d and d not in doms:
                doms.append(d)
        doms = doms[:5]

        for dom in doms:
            try:
                job_id = enqueue_async_scan(
                    dom,
                    industry=str(industry).strip() if industry else None,
                    company_name=company,
                    scan_depth="fast",
                )
                result = poll_scan_job(job_id, timeout_sec=480.0, interval_sec=2.5)
            except Exception as e:
                logger.exception("enterprise scan failed client=%s domain=%s", cid, dom)
                errors.append(f"{cid}/{dom}: {e!s}")
                continue

            score = result.get("score")
            grade = result.get("grade")
            findings = _findings_json(result)

            ins = httpx.post(
                f"{SUPABASE_URL}/rest/v1/client_domain_scans",
                headers=_headers(),
                json={
                    "client_id": cid,
                    "domain": dom,
                    "hawk_score": int(score) if isinstance(score, (int, float)) else None,
                    "grade": str(grade) if grade else None,
                    "findings": findings,
                },
                timeout=30.0,
            )
            if ins.status_code >= 400:
                logger.error("client_domain_scans insert failed: %s", ins.text[:400])
                errors.append(f"{cid}/{dom}: insert {ins.status_code}")
                continue
            scanned += 1

    return {"ok": True, "scanned": scanned, "errors": errors[:30]}
