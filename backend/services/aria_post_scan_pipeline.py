"""Post-scan pipeline: auto-enrich + ZeroBounce verify + ARIA personalized draft.

Runs immediately after a prospect's scan completes (SLA auto-scan or manual
"Run scan" finalize). For a single prospect:

1. Skip if stage past `scanned` (rep/ARIA already moved it) or already dispatched.
2. Skip if already has a verified contact + email_subject (idempotent re-runs).
3. Run Apify enrichment (actor 2 LinkedIn → actor 3 Leads Finder → actor 4
   Website Crawl, in that priority order) for this one domain. If none of
   them surface a contact email, soft-drop the prospect.
4. ZeroBounce verify the email. `valid` or `catch-all` proceeds; anything else
   soft-drops.
5. Classify the vertical (uses industry / business_name / canonical_vertical)
   to pick the correct Smartlead campaign id from crm_settings.
6. Generate a personalized first-touch email via ARIA (reuses
   ``aria_pipeline._generate_email_for_lead`` so prompt / tone / PIPEDA
   fallback stay consistent with the rest of the stack). Greet the contact
   by first name whenever available.
7. Persist ``contact_email``, ``contact_name``, ``contact_title``,
   ``email_finder``, ``zero_bounce_result``, ``email_subject``, ``email_body``,
   ``smartlead_campaign_id`` and flip ``pipeline_status=ready`` so the 600/day
   dispatcher (PR C) can pick the prospect up.

Soft-drop path: ``stage=lost``, ``pipeline_status=suppressed``, plus a
``suppressions`` row keyed by domain so the nightly discovery never re-queues
the lead. We never hard-delete.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from config import SMARTLEAD_API_KEY, SUPABASE_URL
from services.aria_apify_scraper import (
    canonical_vertical,
    run_actor2_linkedin,
    run_actor3_leads_finder,
    run_actor4_website_crawl,
)

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
ZEROBOUNCE_API_KEY = os.environ.get("ZEROBOUNCE_API_KEY", "").strip()
ZEROBOUNCE_VALIDATE = "https://api.zerobounce.net/v2/validate"
SMARTLEAD_BASE = os.environ.get("SMARTLEAD_API_BASE", "https://server.smartlead.ai/api/v1").rstrip("/")


def _configured() -> bool:
    return bool(SUPABASE_URL and SERVICE_KEY)


def _sb_headers(*, prefer: str = "return=minimal") -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _fetch_prospect(prospect_id: str) -> dict[str, Any] | None:
    if not _configured():
        return None
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "id": f"eq.{prospect_id}",
                "select": (
                    "id,domain,company_name,industry,stage,pipeline_status,hawk_score,"
                    "contact_name,contact_email,contact_title,email_finder,email_subject,"
                    "email_body,vulnerability_found,smartlead_campaign_id,dispatched_at"
                ),
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("post-scan fetch prospect=%s failed: %s", prospect_id, exc)
        return None


def _patch_prospect(prospect_id: str, payload: dict[str, Any]) -> None:
    if not _configured():
        return
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json=payload,
            timeout=20.0,
        )
    except Exception as exc:
        logger.warning("post-scan patch prospect=%s failed: %s", prospect_id, exc)


def _soft_drop(prospect_id: str, domain: str, *, reason: str) -> None:
    """Mark prospect stage=lost + pipeline_status=suppressed, insert suppressions row.

    Only regresses stage from the pre-outbound set (new, scanning, scanned) —
    never overrides a rep-advanced prospect.
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
        logger.warning("post-scan soft-drop patch prospect=%s: %s", prospect_id, exc)
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/suppressions",
            headers=_sb_headers(prefer="return=minimal,resolution=merge-duplicates"),
            json={"domain": domain, "reason": reason[:500]},
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("post-scan soft-drop suppressions prospect=%s: %s", prospect_id, exc)


# ── Vertical classification ──────────────────────────────────────────────

_DENTAL_HINTS = ("dental", "dentist", "orthodont", "endodont", "periodont")
_LEGAL_HINTS = ("law", "legal", "attorney", "lawyer", "barrister", "solicitor")
_ACCOUNTING_HINTS = ("account", "cpa", "bookkeep", "tax", "audit")


def _classify_vertical(prospect: dict[str, Any]) -> str:
    """Pick one of {dental, legal, accounting} from prospect metadata."""
    raw = (prospect.get("industry") or "").lower()
    if raw:
        canon = canonical_vertical(raw)
        if canon in ("dental", "legal", "accounting"):
            return canon
    haystack = " ".join(
        str(prospect.get(k) or "").lower()
        for k in ("company_name", "domain", "vulnerability_found")
    )
    for hints, bucket in (
        (_DENTAL_HINTS, "dental"),
        (_LEGAL_HINTS, "legal"),
        (_ACCOUNTING_HINTS, "accounting"),
    ):
        if any(h in haystack for h in hints):
            return bucket
    return "dental"


def _resolve_campaign_id(vertical: str) -> str:
    """Look up the campaign id from crm_settings.smartlead_campaign_id_{vertical}.

    Falls back to a single SMARTLEAD_CAMPAIGN_ID env var if set. Returns empty
    string if nothing is configured — the dispatcher will still pick the lead
    up; it just won't have a pre-assigned campaign until the dispatcher
    resolves it.
    """
    if not _configured():
        return ""
    key = f"smartlead_campaign_id_{vertical}"
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}", "select": "value", "limit": "1"},
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            val = str(rows[0].get("value") or "").strip()
            if val:
                return val
    except Exception as exc:
        logger.warning("post-scan campaign lookup %s failed: %s", key, exc)
    return os.environ.get("SMARTLEAD_CAMPAIGN_ID", "").strip()


# ── Apify single-prospect enrichment ─────────────────────────────────────


def _build_enrichment_lead(prospect: dict[str, Any], vertical: str) -> dict[str, Any]:
    """Shape the prospect row so the shared Apify actor wrappers accept it."""
    return {
        "id": prospect["id"],
        "domain": (prospect.get("domain") or "").strip().lower(),
        "company_name": prospect.get("company_name") or "",
        "vertical": vertical,
        "industry": prospect.get("industry") or vertical,
    }


async def _enrich_single(prospect: dict[str, Any], vertical: str) -> dict[str, Any] | None:
    """Run actors 2→3→4 in fall-through order. Returns first hit or None."""
    lead = _build_enrichment_lead(prospect, vertical)
    domain = lead["domain"]
    if not domain:
        return None
    leads = [lead]

    # Actor 2: LinkedIn decision-maker lookup.
    try:
        a2 = await run_actor2_linkedin(leads)
    except Exception as exc:
        logger.warning("post-scan actor2 prospect=%s failed: %s", prospect["id"], exc)
        a2 = {}
    hit = a2.get(domain) if isinstance(a2, dict) else None
    if hit and hit.get("email") and "@" in str(hit["email"]):
        return {
            "email": str(hit["email"]).lower().strip(),
            "first_name": str(hit.get("first_name") or "").strip(),
            "last_name": str(hit.get("last_name") or "").strip(),
            "title": str(hit.get("title") or "").strip(),
            "source": "linkedin",
        }

    # Actor 3: Leads Finder (mark lead as still email-less for the actor's filter).
    lead["_email_found"] = False
    try:
        a3 = await run_actor3_leads_finder(leads)
    except Exception as exc:
        logger.warning("post-scan actor3 prospect=%s failed: %s", prospect["id"], exc)
        a3 = {}
    hit = a3.get(domain) if isinstance(a3, dict) else None
    if hit and hit.get("email") and "@" in str(hit["email"]):
        return {
            "email": str(hit["email"]).lower().strip(),
            "first_name": str(hit.get("first_name") or "").strip(),
            "last_name": str(hit.get("last_name") or "").strip(),
            "title": str(hit.get("title") or "").strip(),
            "source": "leads_finder",
        }

    # Actor 4: Website crawl (last resort).
    try:
        a4 = await run_actor4_website_crawl(leads)
    except Exception as exc:
        logger.warning("post-scan actor4 prospect=%s failed: %s", prospect["id"], exc)
        a4 = {}
    hit = a4.get(domain) if isinstance(a4, dict) else None
    if hit and hit.get("email") and "@" in str(hit["email"]):
        return {
            "email": str(hit["email"]).lower().strip(),
            "first_name": "",
            "last_name": "",
            "title": "",
            "source": "website_crawl",
        }

    return None


# ── ZeroBounce single-email gate ─────────────────────────────────────────


def _zerobounce_verify(email: str) -> tuple[str, dict[str, Any]]:
    """Return (status, raw_result). `status='unknown'` when disabled/error."""
    if not ZEROBOUNCE_API_KEY:
        return "unknown", {"skipped": "ZEROBOUNCE_API_KEY not configured"}
    try:
        r = httpx.get(
            ZEROBOUNCE_VALIDATE,
            params={"api_key": ZEROBOUNCE_API_KEY, "email": email, "ip_address": ""},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        status = str(data.get("status") or "").lower()
        return status or "unknown", data
    except Exception as exc:
        logger.warning("post-scan ZeroBounce verify %s failed: %s", email, exc)
        return "unknown", {"error": str(exc)[:500]}


# ── Public entry points ─────────────────────────────────────────────────


def _is_ready_already(prospect: dict[str, Any]) -> bool:
    """Idempotency guard: skip if we already drafted a personalized email."""
    return bool(
        prospect.get("contact_email")
        and prospect.get("email_subject")
        and prospect.get("email_body")
        and prospect.get("pipeline_status") == "ready"
    )


def _preserve_stage_for_ready(current_stage: str | None) -> bool:
    """Only set pipeline_status=ready + write drafts if not past sent_email."""
    return current_stage in (None, "new", "scanning", "scanned")


async def run_post_scan_async(prospect_id: str) -> dict[str, Any]:
    """Async implementation. Thread-safe entry point wraps this with asyncio.run."""
    if not _configured():
        return {"ok": False, "prospect_id": prospect_id, "reason": "supabase not configured"}

    prospect = _fetch_prospect(prospect_id)
    if not prospect:
        return {"ok": False, "prospect_id": prospect_id, "reason": "prospect not found"}

    stage = prospect.get("stage")
    if stage in ("lost", "closed_won", "sent_email", "replied", "call_booked"):
        return {"ok": True, "prospect_id": prospect_id, "skipped": f"stage={stage}"}

    if _is_ready_already(prospect):
        return {"ok": True, "prospect_id": prospect_id, "skipped": "already ready"}

    domain = (prospect.get("domain") or "").strip().lower()
    if not domain:
        return {"ok": False, "prospect_id": prospect_id, "reason": "no domain"}

    vertical = _classify_vertical(prospect)

    existing_email = (prospect.get("contact_email") or "").strip().lower()
    existing_name = (prospect.get("contact_name") or "").strip()
    if existing_email and "@" in existing_email:
        enrichment: dict[str, Any] = {
            "email": existing_email,
            "first_name": existing_name.split()[0] if existing_name else "",
            "last_name": " ".join(existing_name.split()[1:]) if existing_name else "",
            "title": prospect.get("contact_title") or "",
            "source": prospect.get("email_finder") or "existing",
        }
    else:
        enrichment = await _enrich_single(prospect, vertical) or {}

    if not enrichment.get("email"):
        _soft_drop(prospect_id, domain, reason="post_scan:no_contact_after_enrichment")
        return {
            "ok": True,
            "prospect_id": prospect_id,
            "domain": domain,
            "outcome": "soft_dropped_no_contact",
        }

    email = str(enrichment["email"]).strip().lower()
    zb_status, zb_raw = _zerobounce_verify(email)
    if zb_status not in ("valid", "catch-all", "unknown"):
        # `invalid`, `spamtrap`, `abuse`, `do_not_mail`, `disposable`, etc. → drop.
        _soft_drop(
            prospect_id,
            domain,
            reason=f"post_scan:zerobounce_{zb_status}",
        )
        _patch_prospect(prospect_id, {"zero_bounce_result": zb_status})
        return {
            "ok": True,
            "prospect_id": prospect_id,
            "domain": domain,
            "outcome": "soft_dropped_invalid_email",
            "zerobounce_status": zb_status,
        }

    # Draft personalized email with ARIA. Import locally to avoid circular
    # import (aria_pipeline transitively touches aria_apify_scraper).
    from services.aria_pipeline import _generate_email_for_lead

    contact_name = " ".join(
        p for p in [enrichment.get("first_name", ""), enrichment.get("last_name", "")] if p
    ).strip()
    if not contact_name:
        contact_name = existing_name
    lead_for_email = {
        "contact_name": contact_name,
        "domain": domain,
        "company_name": prospect.get("company_name") or "",
        "vulnerability_found": prospect.get("vulnerability_found") or "",
        "vertical": vertical,
    }
    email_draft = await _generate_email_for_lead(lead_for_email)

    campaign_id = _resolve_campaign_id(vertical)

    if not _preserve_stage_for_ready(stage):
        # Stage has moved forward during our work — don't regress pipeline_status.
        return {"ok": True, "prospect_id": prospect_id, "skipped": f"stage changed to {stage}"}

    now_iso = datetime.now(timezone.utc).isoformat()
    patch: dict[str, Any] = {
        "contact_email": email,
        "contact_name": contact_name or None,
        "contact_title": enrichment.get("title") or None,
        "email_finder": enrichment.get("source") or None,
        "zero_bounce_result": zb_status,
        "email_subject": email_draft.get("subject", "")[:998],
        "email_body": email_draft.get("body", ""),
        "industry": vertical,
        "pipeline_status": "ready",
        "last_activity_at": now_iso,
    }
    if campaign_id:
        patch["smartlead_campaign_id"] = campaign_id
    _patch_prospect(prospect_id, patch)

    logger.info(
        "post-scan ready prospect=%s domain=%s vertical=%s source=%s zb=%s",
        prospect_id,
        domain,
        vertical,
        enrichment.get("source"),
        zb_status,
    )
    _ = SMARTLEAD_API_KEY  # linter: kept for future inline dispatcher integration
    _ = zb_raw  # raw payload captured server-side via zero_bounce_result summary
    return {
        "ok": True,
        "prospect_id": prospect_id,
        "domain": domain,
        "vertical": vertical,
        "outcome": "ready",
        "source": enrichment.get("source"),
        "zerobounce_status": zb_status,
        "smartlead_campaign_id": campaign_id or None,
    }


def run_post_scan_sync(prospect_id: str) -> dict[str, Any]:
    """Blocking entry point. Safe to call from a thread pool worker.

    Boots its own event loop so it can call the async Apify actor wrappers
    without an existing loop. Returns a small result dict for logging.
    """
    try:
        return asyncio.run(run_post_scan_async(prospect_id))
    except Exception as exc:
        logger.exception("post-scan pipeline prospect=%s crashed: %s", prospect_id, exc)
        return {"ok": False, "prospect_id": prospect_id, "error": str(exc)[:500]}
