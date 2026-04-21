"""Post-scan pipeline: auto-enrich + ARIA personalized draft.

Runs immediately after a prospect's scan completes (SLA auto-scan or manual
"Run scan" finalize). For a single prospect:

1. Skip if stage past `scanned` (rep/ARIA already moved it) or already dispatched.
2. Skip if already has a verified contact + email_subject (idempotent re-runs).
3. Enrich contact via Apollo.io (domain → decision-maker lookup with verified
   email + phone + LinkedIn URL, filtered to ``verified``/``likely to engage``
   statuses only). If Apollo returns nothing, soft-drop.
4. Classify the vertical (uses industry / business_name / canonical_vertical)
   to pick the correct Smartlead campaign id from crm_settings.
5. Generate a personalized first-touch email via ARIA (reuses
   ``aria_pipeline._generate_email_for_lead`` so prompt / tone / PIPEDA
   fallback stay consistent with the rest of the stack). Greet the contact
   by first name whenever available.
6. Persist ``contact_email``, ``contact_name``, ``contact_title``,
   ``contact_phone``, ``contact_linkedin_url``, ``email_finder``,
   ``email_subject``, ``email_body``, ``smartlead_campaign_id`` and flip
   ``pipeline_status=ready`` so the 600/day dispatcher can pick the prospect up.

ZeroBounce is intentionally **disabled** on the verify step — Apollo already
returns only ``verified`` / ``likely to engage`` email statuses (see
``VERTICAL_TITLES`` filter in :mod:`services.apollo_enrichment`) and the
extra ZB hop was soft-dropping too many catch-all domains that do actually
receive mail. The column ``zero_bounce_result`` is still written with
``'skipped'`` so historical analytics queries keep working. The kill switch
lives in ``crm_settings.zerobounce_post_scan_enabled`` — flip to ``true`` to
re-enable without a redeploy.

Soft-drop path: ``stage=lost``, ``pipeline_status=suppressed``, plus a
``suppressions`` row keyed by domain so the nightly discovery never re-queues
the lead. We never hard-delete.

Apollo-miss path (new): when Apollo returns no contact for a domain — which
is the common case for the Canadian SMB long tail (small dental / tax / law
shops Apollo simply doesn't index) — the prospect is routed to
``pipeline_status=va_queue`` instead of soft-dropped, so a human VA can
source the email manually. Stage stays ``scanned``. This unsticks the
``scanned_backlog`` without synthesising contacts or bypassing the verified
gate. Governed by ``crm_settings.apollo_miss_to_va_queue_enabled`` (default
true) — flip to false to restore the old soft-drop behaviour.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from config import SMARTLEAD_API_KEY, SUPABASE_URL
from services.apollo_enrichment import enrich_single_domain
from services.aria_apify_scraper import canonical_vertical
from services.crm_bool_setting import fetch_crm_bool

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
                    "id,domain,company_name,industry,city,province,stage,pipeline_status,hawk_score,"
                    "contact_name,contact_email,contact_title,contact_phone,contact_linkedin_url,"
                    "email_finder,email_subject,email_body,vulnerability_found,"
                    "smartlead_campaign_id,dispatched_at"
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


VaRouteResult = Literal["routed", "kill_switch_off", "guard_filtered", "error"]


def _route_to_va_queue(prospect_id: str, domain: str, *, reason: str) -> VaRouteResult:
    """Move an Apollo-miss prospect into ``pipeline_status=va_queue``.

    Stage stays ``scanned`` — the scan finding is still valid; only the
    automated outreach path is unavailable because Apollo could not source
    a contact. The VA console (``/crm/va``) surfaces every ``va_queue`` row
    regardless of whether ``contact_email`` is populated, so a human can
    LinkedIn / phone / website-scrape the contact and dispatch manually.

    Returns one of:
      * ``routed`` — prospect flipped to ``pipeline_status=va_queue``.
      * ``kill_switch_off`` — ``apollo_miss_to_va_queue_enabled`` is false;
        caller should fall back to the legacy soft-drop behaviour.
      * ``guard_filtered`` — the stage / pipeline_status guard filtered the
        prospect out. Typically means the bulk re-route cron (or a rep)
        already moved it off ``pipeline_status=scanned``; caller MUST NOT
        soft-drop it (that would suppress an already-routed lead).
      * ``error`` — HTTP / network / Supabase failure. Caller MUST NOT
        soft-drop (we don't know the row's real state).
    """
    if not fetch_crm_bool("apollo_miss_to_va_queue_enabled", default=True):
        return "kill_switch_off"
    try:
        # Prefer=return=representation so PostgREST responds with the actual
        # updated rows — a 204 / empty list means the stage+status guard
        # filtered the prospect out (e.g. a rep advanced it past `scanned`
        # or the bulk re-route cron already flipped it to va_queue
        # mid-Apollo) and we must not report a successful route.
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(prefer="return=representation"),
            params={
                "id": f"eq.{prospect_id}",
                "stage": "in.(new,scanning,scanned)",
                "pipeline_status": "eq.scanned",
            },
            json={
                "pipeline_status": "va_queue",
                "last_activity_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json() or []
        if not rows:
            logger.info(
                "post-scan va-route no-op prospect=%s reason=%s (stage/status guard)",
                prospect_id, reason,
            )
            return "guard_filtered"
    except Exception as exc:
        logger.warning(
            "post-scan va-route patch prospect=%s reason=%s: %s",
            prospect_id, reason, exc,
        )
        return "error"
    logger.info(
        "post-scan routed-to-va-queue prospect=%s domain=%s reason=%s",
        prospect_id, domain, reason,
    )
    return "routed"


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
    # Deliberately exclude vulnerability_found — scan findings regularly contain
    # words like "audit" / "law" / "legal hold" which would cross-classify a
    # dental practice into the accounting or legal campaign.
    haystack = " ".join(
        str(prospect.get(k) or "").lower()
        for k in ("company_name", "domain")
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


# ── Apollo single-prospect enrichment ────────────────────────────────────


async def _enrich_single(prospect: dict[str, Any], vertical: str) -> dict[str, Any] | None:
    """Enrich the prospect's decision-maker contact via Apollo.io.

    Replaces the Apify actor 2→3→4 fall-through. Apollo returns verified
    email, first/last name, title, phone, and LinkedIn URL in a single call,
    which is both cheaper and faster. Returns ``None`` when no verified
    contact is found so the caller can soft-drop.
    """
    domain = (prospect.get("domain") or "").strip().lower()
    if not domain:
        return None
    try:
        return await enrich_single_domain(
            domain=domain,
            vertical=vertical,
            company_name=prospect.get("company_name") or "",
            city=prospect.get("city") or None,
            province=prospect.get("province") or None,
        )
    except Exception as exc:
        logger.warning("post-scan apollo enrichment prospect=%s failed: %s", prospect.get("id"), exc)
        return None


# ── ZeroBounce single-email gate ─────────────────────────────────────────


def _zerobounce_verify(email: str) -> tuple[str, dict[str, Any]]:
    """Return (status, raw_result). Gated by ``zerobounce_post_scan_enabled``.

    The post-scan pipeline treats ZeroBounce as an optional tripwire: Apollo's
    own ``contact_email_status`` filter (``verified``/``likely to engage``) is
    already the verified-contact gate. When the CRM toggle is off (current
    default) we short-circuit with ``status='skipped'`` so the prospect
    proceeds to draft + dispatch without a second verification hop. Flip
    ``crm_settings.zerobounce_post_scan_enabled=true`` to re-enable without
    a redeploy.
    """
    if not fetch_crm_bool("zerobounce_post_scan_enabled", default=False):
        return "skipped", {"skipped": "zerobounce_post_scan_enabled=false"}
    if not ZEROBOUNCE_API_KEY:
        return "skipped", {"skipped": "ZEROBOUNCE_API_KEY not configured"}
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
        # Apollo couldn't source a contact — most common for Canadian SMB
        # long-tail (small dental / tax / law shops Apollo doesn't index).
        # Route to VA queue for manual sourcing instead of soft-dropping so
        # the lead is still reachable.
        route_result = _route_to_va_queue(
            prospect_id, domain, reason="post_scan:no_contact_after_enrichment",
        )
        if route_result == "routed":
            return {
                "ok": True,
                "prospect_id": prospect_id,
                "domain": domain,
                "outcome": "routed_to_va_queue",
            }
        if route_result == "guard_filtered":
            # The stage/pipeline_status guard rejected the update — typically
            # means the bulk re-route cron (or a rep) already moved this
            # prospect off `pipeline_status=scanned`. Do NOT soft-drop; that
            # would overwrite va_queue with suppressed and permanently kill
            # an already-routed lead.
            return {
                "ok": True,
                "prospect_id": prospect_id,
                "domain": domain,
                "outcome": "already_routed_or_advanced",
            }
        if route_result == "error":
            # Network / Supabase error — we don't know the row's real state,
            # so leave it alone. The 15-min Pipeline Doctor will retry.
            return {
                "ok": False,
                "prospect_id": prospect_id,
                "domain": domain,
                "outcome": "va_route_error",
            }
        # route_result == "kill_switch_off" → fall back to legacy soft-drop.
        _soft_drop(prospect_id, domain, reason="post_scan:no_contact_after_enrichment")
        return {
            "ok": True,
            "prospect_id": prospect_id,
            "domain": domain,
            "outcome": "soft_dropped_no_contact",
        }

    email = str(enrichment["email"]).strip().lower()
    zb_status, zb_raw = _zerobounce_verify(email)
    # Apollo's verified-status filter is the gate; ZB is an opt-in tripwire
    # only. When ZB *is* enabled, treat `skipped`, `valid`, `catch-all`, or
    # `unknown` as proceed; every other explicit negative still soft-drops.
    if zb_status not in ("skipped", "valid", "catch-all", "unknown"):
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
        "contact_phone": enrichment.get("phone") or None,
        "contact_linkedin_url": enrichment.get("linkedin_url") or None,
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

    # DB-level stage guard. The enrichment + ZeroBounce + OpenAI window can run
    # for minutes; a rep may advance the prospect to sent_email / replied /
    # call_booked during that time. Filtering on stage prevents the final PATCH
    # from regressing pipeline_status back to "ready" on a lead that's already
    # moved forward, matching the pattern used by _soft_drop above and
    # _write_scan_result in aria_sla_auto_scan.
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "id": f"eq.{prospect_id}",
                "stage": "in.(new,scanning,scanned)",
            },
            json=patch,
            timeout=20.0,
        )
    except Exception as exc:
        logger.warning("post-scan final patch prospect=%s failed: %s", prospect_id, exc)

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
