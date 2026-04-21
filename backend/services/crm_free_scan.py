"""Free-scan landing page (securedbyhawk.com/free-scan) — inbound lead capture
with a "3-finding report within 24 hours" promise.

Two phases:

1. **Capture** (:func:`handle_free_scan_lead`)
   - Validates + normalises the submission.
   - Upserts the prospect row (``source='free_scan_landing'``) with whatever
     contact/company/vertical fields the form collected.
   - Flips ``pipeline_status='scanning'`` so the async-scan watchdog picks it
     up the same way the homepage scanner does.
   - Enqueues a deep (``scan_depth='full'``) scan on hawk-scanner-v2.
   - Sends an ack email: *"Your 3-finding report will arrive within 24 hours."*

2. **Dispatch** (:func:`dispatch_pending_free_scan_reports`)
   - Cron pick-work: prospects with ``source='free_scan_landing'``,
     ``scanned_at IS NOT NULL``, ``free_scan_report_sent_at IS NULL``.
   - Pulls the latest ``crm_prospect_scans`` row, chooses the top 3 non-ok
     severity findings in plain English, and mails the report with the
     Cal.com booking CTA.
   - Stamps ``free_scan_report_sent_at`` so we never double-send.

No schema change beyond the one tiny migration
``20260519000001_prospects_free_scan_report_sent_at.sql``.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from services.crm_portal_email import (
    send_free_scan_ack_email,
    send_free_scan_report_email,
)
from services.scanner import enqueue_async_scan

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

FREE_SCAN_SOURCE = "free_scan_landing"

_ALLOWED_VERTICALS = {"dental", "legal", "accounting", "other"}


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def normalize_domain(domain: str) -> str:
    d = (domain or "").lower().strip()
    if d.startswith("http"):
        d = d.split("//", 1)[-1].split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return d.split("/")[0]


def domain_valid(d: str) -> bool:
    if len(d) < 3 or len(d) > 253 or "." not in d:
        return False
    return bool(re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", d, re.I))


def _normalize_vertical(v: str | None) -> str | None:
    if not v:
        return None
    vv = v.strip().lower()
    if vv in _ALLOWED_VERTICALS:
        return None if vv == "other" else vv
    return None


def _severity_rank(severity: str | None) -> int:
    order = {"critical": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 4, "ok": 99}
    return order.get((severity or "").lower(), 50)


def _plain_english(f: dict, interpreted: dict | None) -> str:
    if interpreted:
        plain = interpreted.get("plain_english") or interpreted.get("plainEnglish")
        if isinstance(plain, str) and plain.strip():
            return plain.strip()
    interp = f.get("interpretation")
    if isinstance(interp, str) and interp.strip():
        return interp.strip()
    desc = (f.get("description") or "").strip()
    if desc:
        return desc
    return (f.get("title") or "").strip()


def pick_top_findings(scan_row: dict, limit: int = 3) -> list[dict[str, str]]:
    """Top-``limit`` non-ok findings, severity-sorted, plain English."""
    findings = scan_row.get("findings") or []
    interpreted = scan_row.get("interpreted_findings") or []
    if not isinstance(findings, list):
        return []
    merged: list[tuple[dict, str]] = []
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        ir = interpreted[idx] if idx < len(interpreted) and isinstance(interpreted[idx], dict) else None
        text = _plain_english(f, ir)
        if not text:
            continue
        if (f.get("severity") or "").lower() == "ok":
            continue
        merged.append((f, text))
    merged.sort(key=lambda x: _severity_rank(x[0].get("severity")))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for f, text in merged:
        if text in seen:
            continue
        seen.add(text)
        sev = (f.get("severity") or "medium").lower()
        if sev not in ("critical", "high", "medium", "warning", "low", "info"):
            sev = "medium"
        out.append({"text": text, "severity": sev, "title": (f.get("title") or "").strip()})
        if len(out) >= limit:
            break
    return out


def handle_free_scan_lead(
    *,
    email: str,
    domain: str,
    name: str | None,
    company_name: str | None,
    vertical: str | None,
    enqueue_scan: bool = True,
) -> dict[str, Any]:
    """Upsert prospect, enqueue full scan, send ack email. Always returns ``ok=true``.

    Supabase / Resend failures are logged but never 5xx the landing page — we
    never want to show a US business owner an error on the conversion flow.
    """
    domain = normalize_domain(domain)
    email = (email or "").strip().lower()

    if not domain or not domain_valid(domain):
        return {"ok": True, "accepted": False, "reason": "invalid_domain"}
    if "@" not in email:
        return {"ok": True, "accepted": False, "reason": "invalid_email"}

    vertical_norm = _normalize_vertical(vertical)
    name_clean = (name or "").strip()[:200] or None
    company_clean = (company_name or "").strip()[:200] or None

    now_iso = datetime.now(timezone.utc).isoformat()
    prospect_id: str | None = None

    if SUPABASE_URL and SERVICE_KEY:
        try:
            pr = httpx.get(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
                params={"domain": f"eq.{domain}", "select": "id,source", "limit": "1"},
                timeout=20.0,
            )
            pr.raise_for_status()
            existing = pr.json() or []
            patch: dict[str, Any] = {
                "contact_email": email,
                "source": FREE_SCAN_SOURCE,
                "pipeline_status": "scanning",
                "last_activity_at": now_iso,
            }
            if name_clean:
                patch["contact_name"] = name_clean
            if company_clean:
                patch["company_name"] = company_clean
            if vertical_norm:
                patch["industry"] = vertical_norm

            if existing:
                prospect_id = existing[0]["id"]
                # On re-submission we clear both ``scanned_at`` and
                # ``free_scan_report_sent_at``. Together they move the prospect
                # back to the dispatch queue's eligibility window: dispatch
                # only fires when ``scanned_at IS NOT NULL AND
                # free_scan_report_sent_at IS NULL``. Without clearing
                # ``scanned_at`` we would re-send a report from the *old*
                # scan the instant the cron runs — before the new scan has
                # even completed — and the recipient would get a stale
                # report ahead of the fresh one.
                patch_with_reset: dict[str, Any] = {
                    **patch,
                    "scanned_at": None,
                    "free_scan_report_sent_at": None,
                }
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/prospects",
                    headers=_sb_headers(),
                    params={"id": f"eq.{prospect_id}"},
                    json=patch_with_reset,
                    timeout=20.0,
                ).raise_for_status()
            else:
                row = {
                    "domain": domain,
                    "stage": "scanning",
                    "hawk_score": 0,
                    "created_at": now_iso,
                    **patch,
                }
                ins = httpx.post(
                    f"{SUPABASE_URL}/rest/v1/prospects",
                    headers=_sb_headers(),
                    json=row,
                    timeout=20.0,
                )
                ins.raise_for_status()
                body = ins.json() or []
                if body and isinstance(body, list):
                    prospect_id = body[0].get("id")
        except Exception:
            logger.exception("free-scan: supabase upsert failed domain=%s", domain)

    if enqueue_scan:
        try:
            job_id = enqueue_async_scan(domain, vertical_norm, company_clean, scan_depth="full")
            if prospect_id and SUPABASE_URL and SERVICE_KEY and job_id:
                try:
                    httpx.patch(
                        f"{SUPABASE_URL}/rest/v1/prospects",
                        headers=_sb_headers(),
                        params={"id": f"eq.{prospect_id}"},
                        json={
                            "active_scan_job_id": str(job_id),
                            "scan_started_at": now_iso,
                            "scan_trigger": "free_scan_landing",
                        },
                        timeout=20.0,
                    ).raise_for_status()
                except Exception:
                    logger.exception("free-scan: stamp scan job failed prospect_id=%s", prospect_id)
        except Exception:
            logger.exception("free-scan: enqueue scan failed domain=%s", domain)

    try:
        send_free_scan_ack_email(
            to_email=email,
            domain=domain,
            first_name=name_clean,
        )
    except Exception:
        logger.exception("free-scan: ack email failed domain=%s email=%s", domain, email)

    return {"ok": True, "accepted": True, "prospect_id": prospect_id}


def dispatch_pending_free_scan_reports(limit: int = 100) -> dict[str, Any]:
    """Pick free-scan leads whose scan has completed but haven't been mailed yet.

    Returns ``{sent, skipped, errors}`` counts. Safe to run every few minutes;
    the partial index backs the lookup.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": True, "mode": "stub", "sent": 0, "skipped": 0, "errors": 0}

    sent = 0
    skipped = 0
    errors = 0
    try:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
                "Content-Type": "application/json",
            },
            params={
                "select": "id,domain,contact_email,contact_name,company_name,industry,hawk_score,scanned_at",
                "source": f"eq.{FREE_SCAN_SOURCE}",
                "scanned_at": "not.is.null",
                "free_scan_report_sent_at": "is.null",
                "contact_email": "not.is.null",
                "order": "scanned_at.asc",
                "limit": str(max(1, min(limit, 500))),
            },
            timeout=25.0,
        )
        pr.raise_for_status()
        candidates = pr.json() or []
    except Exception:
        logger.exception("free-scan-dispatch: supabase lookup failed")
        return {"ok": False, "sent": 0, "skipped": 0, "errors": 1}

    for row in candidates:
        prospect_id = row.get("id")
        email = (row.get("contact_email") or "").strip().lower()
        domain = (row.get("domain") or "").strip().lower()
        if not prospect_id or not email or not domain:
            skipped += 1
            continue

        try:
            sr = httpx.get(
                f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
                headers=_sb_headers(),
                params={
                    "prospect_id": f"eq.{prospect_id}",
                    "select": "hawk_score,grade,findings,interpreted_findings",
                    "order": "created_at.desc",
                    "limit": "1",
                },
                timeout=20.0,
            )
            sr.raise_for_status()
            scans = sr.json() or []
        except Exception:
            logger.exception("free-scan-dispatch: scan lookup failed prospect_id=%s", prospect_id)
            errors += 1
            continue

        if not scans:
            skipped += 1
            continue

        scan = scans[0]
        top = pick_top_findings(scan, limit=3)
        if not top:
            skipped += 1
            continue

        try:
            send_free_scan_report_email(
                to_email=email,
                domain=domain,
                first_name=(row.get("contact_name") or "").split(" ")[0] or None,
                hawk_score=(
                    scan.get("hawk_score")
                    if scan.get("hawk_score") is not None
                    else row.get("hawk_score")
                ),
                grade=scan.get("grade"),
                findings=top,
                industry=row.get("industry"),
            )
        except Exception:
            logger.exception("free-scan-dispatch: send failed prospect_id=%s", prospect_id)
            errors += 1
            continue

        try:
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
                params={"id": f"eq.{prospect_id}"},
                json={
                    "free_scan_report_sent_at": datetime.now(timezone.utc).isoformat(),
                    "last_activity_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=20.0,
            ).raise_for_status()
            sent += 1
        except Exception:
            logger.exception("free-scan-dispatch: mark-sent failed prospect_id=%s", prospect_id)
            errors += 1

    return {"ok": True, "sent": sent, "skipped": skipped, "errors": errors, "candidates": len(candidates)}
