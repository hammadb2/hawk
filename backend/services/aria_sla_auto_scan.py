"""SLA auto-scan: any prospect stuck in stage=new for > 10 min gets auto-scanned.

Flow (runs every ~2 min via APScheduler):
1. Query prospects where stage='new' AND active_scan_job_id is null AND
   scanned_at is null AND created_at <= now() - 10 min.
2. For each (concurrency capped), POST hawk-scanner-v2 /v1/scan/async, write
   active_scan_job_id + scan_started_at + scan_trigger='sla_auto' on the row.
3. Poll /v1/jobs/{id} up to ~6 min, write hawk_score + vulnerability_found +
   pipeline_status='scanned' + stage='scanned' + scanned_at on complete.
4. Gate: if hawk_score >= 85 (too secure — no sales opportunity) soft-drop
   the lead: stage='lost', pipeline_status='suppressed', plus a suppressions
   row so the nightly pipeline never re-discovers the domain.

Also runs a watchdog: any prospect with active_scan_job_id older than
SLA_SCAN_WATCHDOG_MIN gets its job_id cleared so it's re-eligible next run.
This protects against worker crashes mid-scan.
"""

from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

SLA_SCAN_AGE_MIN = int(os.environ.get("SLA_SCAN_AGE_MIN", "10"))
SLA_SCAN_WATCHDOG_MIN = int(os.environ.get("SLA_SCAN_WATCHDOG_MIN", "15"))
SLA_SCAN_BATCH = int(os.environ.get("SLA_SCAN_BATCH", "10"))
SLA_SCAN_CONCURRENCY = int(os.environ.get("SLA_SCAN_CONCURRENCY", "3"))
SLA_SCORE_DROP_THRESHOLD = int(os.environ.get("SLA_SCORE_DROP_THRESHOLD", "85"))


def _sb_headers(*, prefer: str = "return=minimal") -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _configured() -> bool:
    return bool(SUPABASE_URL and SERVICE_KEY)


def _watchdog_release_stuck_jobs() -> int:
    """Clear active_scan_job_id on prospects whose scan started > watchdog ago.

    Returns number of rows released.
    """
    if not _configured():
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=SLA_SCAN_WATCHDOG_MIN)).isoformat()
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(prefer="return=representation,count=exact"),
            params={
                "active_scan_job_id": "not.is.null",
                "scan_started_at": f"lt.{cutoff}",
            },
            json={"active_scan_job_id": None, "scan_started_at": None},
            timeout=20.0,
        )
        if r.status_code >= 400:
            logger.warning("SLA watchdog release failed: %s %s", r.status_code, r.text[:300])
            return 0
        try:
            return len(r.json() or [])
        except Exception:
            return 0
    except Exception as exc:
        logger.warning("SLA watchdog release error: %s", exc)
        return 0


def _find_candidates(limit: int) -> list[dict[str, Any]]:
    """Prospects stuck in stage=new with no active scan and no prior scan."""
    if not _configured():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=SLA_SCAN_AGE_MIN)).isoformat()
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "select": "id,domain,company_name,industry",
                "stage": "eq.new",
                "active_scan_job_id": "is.null",
                "scanned_at": "is.null",
                "created_at": f"lte.{cutoff}",
                "order": "created_at.asc",
                "limit": str(limit),
            },
            timeout=20.0,
        )
        r.raise_for_status()
        return list(r.json() or [])
    except Exception as exc:
        logger.warning("SLA candidates fetch error: %s", exc)
        return []


def _claim_prospect(prospect_id: str, job_id: str) -> bool:
    """Claim a prospect for scanning by atomically writing active_scan_job_id.

    Uses ``Prefer: return=representation`` so PostgREST returns the affected
    rows; if the length is 0, another worker already claimed it.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(prefer="return=representation"),
            params={
                "id": f"eq.{prospect_id}",
                "active_scan_job_id": "is.null",  # only claim if no existing job
            },
            json={
                "active_scan_job_id": job_id,
                "scan_started_at": now,
                "scan_last_polled_at": now,
                "scan_trigger": "sla_auto",
            },
            timeout=15.0,
        )
        if r.status_code >= 400:
            return False
        try:
            body = r.json() or []
        except Exception:
            body = []
        return len(body) > 0
    except Exception as exc:
        logger.warning("SLA claim error prospect=%s: %s", prospect_id, exc)
        return False


def _update_job_id(prospect_id: str, job_id: str) -> None:
    """Replace the placeholder claim token with the real scanner job_id."""
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json={"active_scan_job_id": job_id},
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("SLA update-job-id error prospect=%s: %s", prospect_id, exc)


def _soft_drop(prospect_id: str, domain: str, *, reason: str) -> None:
    """Mark prospect stage=lost + pipeline_status=suppressed, insert suppressions row."""
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json={
                "stage": "lost",
                "pipeline_status": "suppressed",
                "active_scan_job_id": None,
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("SLA soft-drop patch error prospect=%s: %s", prospect_id, exc)
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/suppressions",
            headers=_sb_headers(prefer="return=minimal,resolution=merge-duplicates"),
            json={"domain": domain, "reason": reason[:500]},
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("SLA soft-drop suppression error prospect=%s: %s", prospect_id, exc)


def _write_scan_result(prospect_id: str, result: dict[str, Any]) -> int | None:
    """Persist scan result (hawk_score, vulnerability_found). Returns score."""
    score = result.get("score")
    try:
        score_int: int | None = int(score) if score is not None else None
    except (TypeError, ValueError):
        score_int = None

    findings = result.get("findings") or []
    severity_order = {"critical": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 4}
    top = None
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = (f.get("severity") or "info").lower()
        if top is None or severity_order.get(sev, 99) < severity_order.get(
            (top.get("severity") or "info").lower(), 99
        ):
            top = f

    vuln_text = ""
    vuln_type = None
    if top:
        title = top.get("title") or top.get("name") or ""
        interp = top.get("interpretation") or top.get("plain_english") or top.get("description") or ""
        severity = (top.get("severity") or "").upper()
        vuln_type = severity or None
        vuln_text = f"[{severity}] {title}".strip()
        if interp:
            vuln_text += f" \u2014 {str(interp)[:200]}"

    patch: dict[str, Any] = {
        "pipeline_status": "scanned",
        "stage": "scanned",
        "active_scan_job_id": None,
        "scan_started_at": None,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
    if score_int is not None:
        patch["hawk_score"] = max(0, min(100, score_int))
    if vuln_text:
        patch["vulnerability_found"] = vuln_text[:10000]
    if vuln_type:
        patch["vulnerability_type"] = vuln_type[:500]
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json=patch,
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("SLA scan result patch error prospect=%s: %s", prospect_id, exc)

    return score_int


def _release_on_failure(prospect_id: str, error: str) -> None:
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json={
                "active_scan_job_id": None,
                "scan_started_at": None,
                "vulnerability_found": f"[SCAN FAILED] {error[:200]}",
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("SLA release-on-failure error prospect=%s: %s", prospect_id, exc)


def _scan_one(prospect: dict[str, Any]) -> dict[str, Any]:
    from services.scanner import enqueue_async_scan, poll_scan_job

    prospect_id = str(prospect["id"])
    domain = str(prospect.get("domain") or "").strip().lower()
    if not domain:
        return {"prospect_id": prospect_id, "skipped": "no_domain"}

    # Claim first (atomically, with a local placeholder UUID) so we don't burn
    # scanner credits on prospects another worker is already handling.
    placeholder = str(uuid.uuid4())
    if not _claim_prospect(prospect_id, placeholder):
        logger.info("SLA skip prospect=%s: already claimed", prospect_id)
        return {"prospect_id": prospect_id, "skipped": "already_claimed"}

    try:
        job_id = enqueue_async_scan(
            domain,
            industry=prospect.get("industry"),
            company_name=prospect.get("company_name"),
            scan_depth="full",
            trust_level="public",
        )
    except Exception as exc:
        _release_on_failure(prospect_id, f"enqueue: {exc}")
        return {"prospect_id": prospect_id, "error": f"enqueue: {exc}"}

    _update_job_id(prospect_id, job_id)

    try:
        result = poll_scan_job(job_id, timeout_sec=360.0, interval_sec=5.0)
    except Exception as exc:
        _release_on_failure(prospect_id, f"poll: {exc}")
        return {"prospect_id": prospect_id, "error": f"poll: {exc}"}

    score = _write_scan_result(prospect_id, result)
    if score is not None and score >= SLA_SCORE_DROP_THRESHOLD:
        _soft_drop(prospect_id, domain, reason=f"sla_auto_score_gate:hawk_score={score}>=threshold")
        return {"prospect_id": prospect_id, "domain": domain, "score": score, "outcome": "soft_dropped"}
    return {"prospect_id": prospect_id, "domain": domain, "score": score, "outcome": "scanned"}


def run_sla_auto_scan() -> dict[str, Any]:
    """Public entrypoint used by the APScheduler job."""
    if not _configured():
        return {"ok": False, "reason": "supabase not configured"}

    released = _watchdog_release_stuck_jobs()
    candidates = _find_candidates(SLA_SCAN_BATCH)
    if not candidates:
        return {"ok": True, "released": released, "scanned": 0, "soft_dropped": 0, "errors": 0}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=SLA_SCAN_CONCURRENCY) as pool:
        for res in pool.map(_scan_one, candidates):
            results.append(res)

    scanned = sum(1 for r in results if r.get("outcome") == "scanned")
    dropped = sum(1 for r in results if r.get("outcome") == "soft_dropped")
    errors = sum(1 for r in results if "error" in r)
    return {
        "ok": True,
        "released": released,
        "candidates": len(candidates),
        "scanned": scanned,
        "soft_dropped": dropped,
        "errors": errors,
        "results": results[:50],
    }
