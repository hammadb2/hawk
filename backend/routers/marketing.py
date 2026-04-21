"""Public marketing endpoints — homepage lead capture + /free-scan (no auth)."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from services.crm_free_scan import handle_free_scan_lead
from services.crm_portal_email import send_homepage_scan_followup_email
from services.scanner import enqueue_async_scan

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketing"])


class _FreeScanRateLimiter:
    """Simple in-memory sliding-window rate limiter keyed by client IP.

    Conservative for the free-scan endpoint: 3 submissions per minute per IP
    is plenty for a real user and enough to deflect a low-effort form-spam
    attempt without needing Cloudflare Turnstile up front.
    """

    def __init__(self, max_requests: int = 3, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_prune: float = 0.0

    def check(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune > 300:
                self._hits = {
                    k: v for k, v in self._hits.items()
                    if v and now - v[-1] < self._window
                }
                self._last_prune = now
            hits = self._hits.get(key, [])
            hits = [t for t in hits if now - t < self._window]
            if len(hits) >= self._max:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


_free_scan_limiter = _FreeScanRateLimiter(max_requests=3, window_seconds=60)


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _normalize_domain(domain: str) -> str:
    d = domain.lower().strip()
    if d.startswith("http"):
        d = d.split("//", 1)[-1].split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def _domain_valid(d: str) -> bool:
    if len(d) < 3 or len(d) > 253 or "." not in d:
        return False
    return bool(re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", d, re.I))


class HomepageLeadBody(BaseModel):
    email: EmailStr
    domain: str = Field(..., min_length=1)
    hawk_score: int | None = None
    grade: str | None = None
    top_finding: str | None = Field(None, max_length=2000)
    findings_plain: list[str] = Field(default_factory=list, max_length=20)


def _enqueue_full_scan_background(domain: str) -> None:
    """Queue deep scan for ops / ARIA pipeline (non-blocking)."""
    try:
        enqueue_async_scan(domain, None, None, scan_depth="full")
    except Exception:
        logger.exception("homepage-lead: enqueue full scan failed domain=%s", domain)


@router.post("/api/marketing/homepage-lead")
def homepage_lead(body: HomepageLeadBody, background_tasks: BackgroundTasks) -> dict[str, str]:
    """
    Save homepage email capture to Supabase prospects and send Resend follow-up.
    Always returns ok=true for UX; failures are logged only.
    """
    domain = _normalize_domain(body.domain)
    email = str(body.email).strip().lower()
    if not domain or not _domain_valid(domain):
        logger.warning("homepage-lead: bad domain %s", domain)
        return {"ok": "true"}

    if not SUPABASE_URL or not SERVICE_KEY:
        logger.warning("homepage-lead: Supabase not configured")
        try:
            send_homepage_scan_followup_email(
                to_email=email,
                domain=domain,
                hawk_score=body.hawk_score,
                grade=body.grade,
                findings_plain=body.findings_plain[:12],
            )
        except Exception:
            logger.exception("homepage-lead: email only path failed")
        background_tasks.add_task(_enqueue_full_scan_background, domain)
        return {"ok": "true"}

    row: dict[str, Any] = {
        "domain": domain,
        "contact_email": email,
        "hawk_score": body.hawk_score if body.hawk_score is not None else 0,
        "source": "homepage_scanner",
        "stage": "scanned",
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.top_finding:
        row["top_finding"] = body.top_finding[:2000]

    try:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb(),
            params={"domain": f"eq.{domain}", "select": "id", "limit": "1"},
            timeout=20.0,
        )
        pr.raise_for_status()
        existing = pr.json() or []
        if existing:
            pid = existing[0]["id"]
            patch: dict[str, Any] = {
                "contact_email": email,
                "hawk_score": row["hawk_score"],
                "source": "homepage_scanner",
                "last_activity_at": row["last_activity_at"],
            }
            if body.top_finding:
                patch["top_finding"] = body.top_finding[:2000]
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb(),
                params={"id": f"eq.{pid}"},
                json=patch,
                timeout=20.0,
            ).raise_for_status()
        else:
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb(),
                json=row,
                timeout=20.0,
            ).raise_for_status()
    except Exception:
        logger.exception("homepage-lead: Supabase upsert failed domain=%s email=%s", domain, email)

    try:
        send_homepage_scan_followup_email(
            to_email=email,
            domain=domain,
            hawk_score=body.hawk_score,
            grade=body.grade,
            findings_plain=body.findings_plain[:12],
        )
    except Exception:
        logger.exception("homepage-lead: Resend failed domain=%s email=%s", domain, email)

    background_tasks.add_task(_enqueue_full_scan_background, domain)

    return {"ok": "true"}


class FreeScanBody(BaseModel):
    """Submission shape for `POST /api/marketing/free-scan`.

    `vertical` lets us route the prospect into the right regulatory-angle
    email template (HIPAA for dental, FTC Safeguards for accounting, ABA 24-514
    for legal). Anything else — or omitted — becomes a generic US SMB angle.
    """

    name: str = Field("", max_length=200)
    email: EmailStr
    domain: str = Field(..., min_length=1)
    company_name: str | None = Field(None, max_length=200)
    vertical: str | None = Field(None, max_length=50)


@router.post("/api/marketing/free-scan")
def free_scan_submit(body: FreeScanBody, request: Request) -> dict[str, Any]:
    """Public endpoint for the /free-scan landing page.

    Flow:
      1. Rate-limit by client IP (3/min).
      2. Hand off to :func:`handle_free_scan_lead` which upserts the prospect
         with ``source='free_scan_landing'``, flips it into ``scanning``,
         enqueues the async full scan, and sends the 24-hour ack email.
      3. A separate cron (``/api/crm/cron/free-scan-dispatch-reports``) picks
         up scans that have finished and mails the 3-finding report.

    Always returns ``200`` + ``{ok: true}`` on well-formed input so the landing
    page can show a unified success state regardless of downstream hiccups
    (Supabase / Resend / scanner). Invalid domain / email yields 400.
    """
    client_ip = _client_ip(request)
    if not _free_scan_limiter.check(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again in a minute.",
        )

    result = handle_free_scan_lead(
        email=str(body.email),
        domain=body.domain,
        name=body.name,
        company_name=body.company_name,
        vertical=body.vertical,
    )
    if not result.get("accepted"):
        reason = result.get("reason") or "invalid_input"
        raise HTTPException(status_code=400, detail=reason)
    return {"ok": True}
