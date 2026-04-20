"""Public marketing endpoints — homepage lead capture (no auth)."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field

from services.crm_portal_email import send_homepage_scan_followup_email
from services.scanner import enqueue_async_scan

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketing"])

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
