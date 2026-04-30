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
# Defaults sized for production scanner pool: 40 domains per tick, 20 concurrent
# Charlotte scans. Override via env on Railway / Hetzner if a smaller
# environment can't keep up. The previous 10/3 defaults were dev-tier and
# couldn't keep up with the post-scan filter feeding Charlotte at peak.
SLA_SCAN_BATCH = int(os.environ.get("SLA_SCAN_BATCH", "40"))
SLA_SCAN_CONCURRENCY = int(os.environ.get("SLA_SCAN_CONCURRENCY", "20"))
# Stuck-post-scan sweep is cheap (Apollo + OpenAI per prospect, no Apify)
# compared with fresh scans, so it runs on a bigger batch/concurrency budget
# to chew through backlogs like the 800-prospect incident without waiting a
# couple of hours for the 10-per-tick SLA budget.
SLA_STUCK_BATCH = int(os.environ.get("SLA_STUCK_BATCH", "75"))
SLA_STUCK_CONCURRENCY = int(os.environ.get("SLA_STUCK_CONCURRENCY", "8"))
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

    Does NOT touch ``stage``. Stuck rows are recovered by the candidate query
    which matches ``stage in (new, scanning)`` and ``active_scan_job_id is null``.
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
                # Only release SLA-auto scans. Manual scans can legitimately
                # run up to ~20 min on the frontend poll loop; they clear
                # themselves via the finalize route.
                "scan_trigger": "eq.sla_auto",
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
    """Prospects needing a scan.

    Matches both ``stage=new`` (never scanned) and ``stage=scanning``
    (previously claimed but then orphaned — e.g. scanner crashed, network
    blip during _release_on_failure). Either way, as long as
    ``active_scan_job_id`` is clear and ``scanned_at`` is null, the row is
    fair game to re-claim. This is the self-healing recovery path for any
    partial-failure of the scan lifecycle.
    """
    if not _configured():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=SLA_SCAN_AGE_MIN)).isoformat()
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "select": "id,domain,company_name,industry",
                "stage": "in.(new,scanning)",
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

    Also transitions ``stage`` to ``scanning`` so the pipeline board reflects
    the in-flight scan in real time. The stage filter accepts both ``new``
    (first-time claim) and ``scanning`` (re-claim after an orphaned previous
    attempt). Uses ``Prefer: return=representation`` so PostgREST returns
    affected rows; if length is 0, another worker already claimed it or a rep
    advanced past these stages in the last second.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(prefer="return=representation"),
            params={
                "id": f"eq.{prospect_id}",
                "active_scan_job_id": "is.null",  # only claim if no existing job
                "stage": "in.(new,scanning)",
            },
            json={
                "active_scan_job_id": job_id,
                "scan_started_at": now,
                "scan_last_polled_at": now,
                "scan_trigger": "sla_auto",
                "stage": "scanning",
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
    """Mark prospect stage=lost + pipeline_status=suppressed, insert suppressions row.

    Only applies the stage change if the prospect is still at ``new``,
    ``scanning``, or ``scanned`` — we never regress a rep-advanced prospect
    (sent_email, replied, call_booked, closed_won).
    """
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "id": f"eq.{prospect_id}",
                "stage": "in.(new,scanning,scanned)",
            },
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


def _write_scan_result(
    prospect_id: str,
    result: dict[str, Any],
    *,
    job_id: str | None = None,
) -> int | None:
    """Persist scan result (hawk_score, vulnerability_found). Returns score.

    Also inserts a row into ``crm_prospect_scans`` with the full scanner payload
    so the prospect detail panel's "Scan results" tab surfaces the same data the
    manual Scan button produces. Without this row the card's score badge would
    show a number while the detail panel still said "No scans yet".
    """
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

    # Split into two PATCHes: the first unconditionally refreshes scan-state
    # fields (score, findings, timing), the second advances stage only if the
    # prospect hasn't been manually progressed past `new` during the poll window.
    # Default these to None so a successful retry after a prior failure (which
    # may have written "[SCAN FAILED] …" into vulnerability_found via
    # _release_on_failure) clears the stale message. They're overwritten below
    # if the current scan produced findings.
    scan_patch: dict[str, Any] = {
        "active_scan_job_id": None,
        "scan_started_at": None,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "vulnerability_found": None,
        "vulnerability_type": None,
    }
    if score_int is not None:
        scan_patch["hawk_score"] = max(0, min(100, score_int))
    if vuln_text:
        scan_patch["vulnerability_found"] = vuln_text[:10000]
    if vuln_type:
        scan_patch["vulnerability_type"] = vuln_type[:500]
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json=scan_patch,
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("SLA scan result patch (scan fields) error prospect=%s: %s", prospect_id, exc)

    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "id": f"eq.{prospect_id}",
                # Only advance from `new` (never scanned) or `scanning` (the
                # claim-time transition); never regress later stages if a rep
                # manually advanced the prospect during the scan.
                "stage": "in.(new,scanning)",
            },
            json={"stage": "scanned", "pipeline_status": "scanned"},
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("SLA scan result patch error prospect=%s: %s", prospect_id, exc)

    # Persist a crm_prospect_scans row so the prospect detail "Scan results"
    # tab has the full interpreted + attack-path payload to render. Idempotent
    # via external_job_id when available.
    try:
        raw_layers = result.get("raw_layers") or {}
        interpreted = result.get("interpreted_findings") or []
        if not interpreted and isinstance(raw_layers, dict):
            interpreted = raw_layers.get("interpreted_findings") or []
        attack_paths = result.get("attack_paths") or []
        if not attack_paths and isinstance(raw_layers, dict):
            attack_paths = raw_layers.get("attack_paths") or []
        breach_cost = result.get("breach_cost_estimate") or {}
        industry = result.get("industry")

        # Stash insurance_readiness inside the findings JSON so the post-scan
        # filter (#15) can read it without needing a new schema column.
        # The scanner returns it as a top-level key.
        ins = result.get("insurance_readiness")
        findings_payload: dict[str, Any] = {
            "source": "hawk_scanner_v2_async_sla",
            "findings": findings,
        }
        if isinstance(ins, dict) and ins:
            findings_payload["insurance_readiness"] = ins

        scan_row: dict[str, Any] = {
            "prospect_id": prospect_id,
            "hawk_score": score_int if score_int is not None else 0,
            "grade": result.get("grade"),
            "findings": findings_payload,
            "status": "complete",
            "scan_version": result.get("scan_version") or "2.0",
            "industry": industry,
            "raw_layers": raw_layers if isinstance(raw_layers, dict) else {},
            "interpreted_findings": interpreted,
            "breach_cost_estimate": breach_cost if isinstance(breach_cost, dict) else {},
            "attack_paths": attack_paths if isinstance(attack_paths, list) else [],
        }
        if job_id:
            scan_row["external_job_id"] = job_id

        httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
            headers=_sb_headers(prefer="return=minimal,resolution=merge-duplicates"),
            json=scan_row,
            timeout=20.0,
        )
    except Exception as exc:
        logger.warning("SLA scan result crm_prospect_scans insert error prospect=%s: %s", prospect_id, exc)

    return score_int


def _release_on_failure(prospect_id: str, error: str) -> None:
    """Clear the scan lock on failure in a single atomic PATCH.

    The stage stays at ``scanning`` so the UI reflects the attempt; the
    candidate query matches ``stage in (new, scanning)`` with
    ``active_scan_job_id is null`` and will re-pick the prospect on the next
    scheduler tick for a retry. This avoids the two-step failure window where
    one PATCH could succeed and the other fail, leaving the prospect
    unrecoverable.
    """
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

    score = _write_scan_result(prospect_id, result, job_id=job_id)
    if score is not None and score >= SLA_SCORE_DROP_THRESHOLD:
        _soft_drop(prospect_id, domain, reason=f"sla_auto_score_gate:hawk_score={score}>=threshold")
        return {"prospect_id": prospect_id, "domain": domain, "score": score, "outcome": "soft_dropped"}

    # Scan succeeded + score < threshold → kick off enrichment + ZeroBounce +
    # ARIA personalized draft in the same worker thread. Blocking here is fine
    # because SLA_SCAN_CONCURRENCY is already capped and the SLA job only runs
    # every couple of minutes. A failure here must not regress the scan
    # completion itself, so swallow exceptions.
    post_scan_outcome: str | None = None
    try:
        from services.aria_post_scan_pipeline import run_post_scan_sync

        ps = run_post_scan_sync(prospect_id)
        post_scan_outcome = str(ps.get("outcome") or ps.get("skipped") or "")
    except Exception as exc:
        logger.warning("SLA post-scan pipeline prospect=%s failed: %s", prospect_id, exc)

    return {
        "prospect_id": prospect_id,
        "domain": domain,
        "score": score,
        "outcome": "scanned",
        "post_scan": post_scan_outcome,
    }


def _find_stuck_post_scan(limit: int) -> list[dict[str, Any]]:
    """Find prospects that finished scanning but never got fully enriched.

    These are prospects whose manual finalize route fired-and-forgot the
    post-scan trigger but the HTTP call failed (backend down, network
    blip), leaving the prospect at ``stage=scanned, pipeline_status=scanned``
    without the full (contact_email + email_subject + smartlead_campaign_id)
    triple needed for the rolling dispatcher. The normal SLA
    ``_find_candidates`` filter misses them (it requires stage in
    (new,scanning) AND scanned_at is null), so we add a dedicated sweep here
    keyed on scanned_at.

    We deliberately do **not** gate on ``contact_email IS NULL`` any more:
    some prospects already had a contact_email copied in from older nightly
    Apollo enrichment but still lack ``email_subject`` or
    ``smartlead_campaign_id``, so the rolling dispatcher's
    ``pipeline_status=eq.ready`` filter skips them forever. The post-scan
    pipeline is idempotent (it short-circuits at the top when the full
    triple is already present), so broadening the filter is safe.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "select": "id,domain,contact_email,email_subject,smartlead_campaign_id",
                "stage": "eq.scanned",
                "pipeline_status": "eq.scanned",
                "scanned_at": f"lt.{cutoff}",
                "or": (
                    "(contact_email.is.null,"
                    "email_subject.is.null,"
                    "smartlead_campaign_id.is.null)"
                ),
                "order": "scanned_at.asc",
                "limit": str(limit),
            },
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("SLA stuck-post-scan query failed: %s", exc)
        return []


def _run_post_scan_one(prospect: dict[str, Any]) -> dict[str, Any]:
    """Swallow exceptions so one stuck prospect can't break the batch."""
    try:
        from services.aria_post_scan_pipeline import run_post_scan_sync

        return run_post_scan_sync(prospect["id"])
    except Exception as exc:
        logger.warning(
            "SLA stuck-post-scan prospect=%s failed: %s", prospect.get("id"), exc
        )
        return {"ok": False, "prospect_id": prospect.get("id"), "error": str(exc)[:200]}


def run_sla_auto_scan() -> dict[str, Any]:
    """Public entrypoint used by the APScheduler job."""
    if not _configured():
        return {"ok": False, "reason": "supabase not configured"}

    released = _watchdog_release_stuck_jobs()

    # Sweep stuck post-scan prospects (manual finalize fire-and-forget that
    # never landed). Run this first so a queue of stuck leads gets unblocked
    # on the same 2-minute tick as fresh scans.
    stuck = _find_stuck_post_scan(SLA_STUCK_BATCH)
    stuck_results: list[dict[str, Any]] = []
    if stuck:
        with ThreadPoolExecutor(max_workers=SLA_STUCK_CONCURRENCY) as pool:
            for res in pool.map(_run_post_scan_one, stuck):
                stuck_results.append(res)

    candidates = _find_candidates(SLA_SCAN_BATCH)
    results: list[dict[str, Any]] = []
    if candidates:
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
        "stuck_post_scan": len(stuck),
        "stuck_results": stuck_results[:25],
        "results": results[:50],
    }
