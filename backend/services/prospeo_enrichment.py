"""Prospeo contact enrichment — primary email finder for the HAWK pipeline.

Two-step flow:
1. ``/search-person`` with ``company.websites`` filter to discover decision-
   makers at a given domain (1 credit per page of 25 results).
2. ``/bulk-enrich-person`` with ``person_id`` to reveal verified emails
   (1 credit per match).

Also supports direct ``/enrich-person`` when a contact name is already known
(e.g. from Google Places).

Return shape matches Apollo's ``enrich_single_domain`` so
``aria_apify_scraper`` and ``aria_post_scan_pipeline`` need zero changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROSPEO_BASE = "https://api.prospeo.io"
PROSPEO_API_KEY = os.environ.get("PROSPEO_API_KEY", "").strip()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Valid Prospeo seniority enum values (discovered empirically):
# Founder/Owner, Director, Manager, Partner, Vice President, Head, Senior
# Invalid: C-Level, CXO, VP, Owner, Founder
VERTICAL_SENIORITIES: dict[str, list[str]] = {
    "dental": ["Founder/Owner", "Director", "Manager"],
    "legal": ["Founder/Owner", "Partner", "Director", "Manager"],
    "accounting": ["Founder/Owner", "Partner", "Director", "Manager"],
}


def _headers() -> dict[str, str]:
    return {
        "X-KEY": PROSPEO_API_KEY,
        "Content-Type": "application/json",
    }


def _configured() -> bool:
    return bool(PROSPEO_API_KEY)


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


# ── Credit tracking ──────────────────────────────────────────────────────


def _fetch_setting(key: str, default: str = "") -> str:
    if not SUPABASE_URL or not SERVICE_KEY:
        return default
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}", "select": "value", "limit": "1"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json() or []
        if rows:
            val = rows[0].get("value")
            return str(val) if val is not None else default
    except Exception as exc:
        logger.warning("prospeo fetch setting %s failed: %s", key, exc)
    return default


def _upsert_setting(key: str, value: str) -> None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"key": key, "value": value},
            timeout=10.0,
        )
    except Exception as exc:
        logger.warning("prospeo upsert setting %s failed: %s", key, exc)


def _increment_credits(n: int) -> None:
    if n <= 0:
        return
    today = date.today().isoformat()
    stored_date = _fetch_setting("prospeo_credits_used_date", "")
    if stored_date != today:
        _upsert_setting("prospeo_credits_used_date", today)
        _upsert_setting("prospeo_credits_used_today", str(n))
    else:
        current = int(_fetch_setting("prospeo_credits_used_today", "0") or 0)
        _upsert_setting("prospeo_credits_used_today", str(current + n))


# ── Search Person by domain ──────────────────────────────────────────────


async def _search_persons_by_domain(
    domain: str,
    vertical: str = "dental",
    *,
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Find decision-makers at a domain via ``/search-person``.

    Returns raw person dicts (no email yet — just person_id + metadata).
    """
    seniorities = VERTICAL_SENIORITIES.get(vertical, VERTICAL_SENIORITIES["dental"])

    payload: dict[str, Any] = {
        "page": 1,
        "filters": {
            "company": {
                "websites": {
                    "include": [domain],
                },
            },
            "person_seniority": {
                "include": seniorities,
            },
        },
    }

    # Try with seniority first, fall back to domain-only search
    for attempt_payload in [payload, {"page": 1, "filters": {"company": {"websites": {"include": [domain]}}}}]:
        try:
            r = await client.post(
                f"{PROSPEO_BASE}/search-person",
                headers=_headers(),
                json=attempt_payload,
            )
            if r.status_code == 429:
                logger.warning("Prospeo search rate limited for domain=%s", domain)
                return []
            if r.status_code >= 400:
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                code = body.get("error_code", "")
                if code == "NO_RESULTS":
                    return []
                if code == "INVALID_FILTERS":
                    continue  # try fallback without seniority
                logger.info("Prospeo search domain=%s HTTP %s code=%s", domain, r.status_code, code)
                return []

            body = r.json()
            if body.get("error"):
                if body.get("error_code") == "NO_RESULTS":
                    return []
                continue

            _increment_credits(1)
            results = body.get("results") or []
            persons = [
                r.get("person", {})
                for r in results
                if isinstance(r, dict) and r.get("person")
            ]
            if persons:
                return persons
        except Exception as exc:
            logger.warning("Prospeo search domain=%s failed: %s", domain, exc)
            return []
    return []


# ── Single enrichment ────────────────────────────────────────────────────


async def enrich_single_domain(
    *,
    domain: str,
    vertical: str,
    company_name: str = "",
    contact_name: str = "",
    city: str | None = None,
    province: str | None = None,
) -> dict[str, Any] | None:
    """Find a verified decision-maker contact for a domain via Prospeo.

    Strategy:
    1. If ``contact_name`` is provided, use ``/enrich-person`` directly.
    2. Otherwise, ``/search-person`` by domain → ``/enrich-person`` by person_id.

    Returns the same shape as ``apollo_enrichment.enrich_single_domain``::

        {
            "email": "jane@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "title": "Managing Partner",
            "phone": "",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "source": "prospeo",
        }

    Returns ``None`` when no verified contact is found.
    """
    if not _configured():
        return None

    domain = (domain or "").strip().lower()
    if not domain:
        return None

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            # Path A: direct enrich when we have a name
            if contact_name:
                return await _enrich_by_name(domain, contact_name, company_name, client=client)

            # Path B: search → enrich by person_id
            persons = await _search_persons_by_domain(domain, vertical, client=client)
            if not persons:
                return None

            # Try top 3 candidates
            for person in persons[:3]:
                pid = person.get("person_id") or person.get("id") or ""
                if not pid:
                    continue
                contact = await _enrich_by_person_id(pid, client=client)
                if contact:
                    return contact

            return None
    except Exception as exc:
        logger.warning("Prospeo enrich_single_domain domain=%s failed: %s", domain, exc)
        return None


async def _enrich_by_name(
    domain: str,
    full_name: str,
    company_name: str = "",
    *,
    client: httpx.AsyncClient,
) -> dict[str, Any] | None:
    """Enrich a person by name + domain."""
    data: dict[str, Any] = {
        "full_name": full_name,
        "company_website": domain,
    }
    if company_name:
        data["company_name"] = company_name

    r = await client.post(
        f"{PROSPEO_BASE}/enrich-person",
        headers=_headers(),
        json={"only_verified_email": True, "data": data},
    )
    if r.status_code >= 400:
        return None
    body = r.json()
    if body.get("error"):
        return None
    _increment_credits(body.get("total_cost", 1))
    return _extract_contact(body)


async def _enrich_by_person_id(
    person_id: str,
    *,
    client: httpx.AsyncClient,
) -> dict[str, Any] | None:
    """Enrich a person by person_id from search results."""
    r = await client.post(
        f"{PROSPEO_BASE}/enrich-person",
        headers=_headers(),
        json={
            "only_verified_email": True,
            "data": {"person_id": person_id},
        },
    )
    if r.status_code >= 400:
        return None
    body = r.json()
    if body.get("error"):
        return None
    _increment_credits(body.get("total_cost", 1))
    return _extract_contact(body)


# ── Bulk enrichment ──────────────────────────────────────────────────────


async def enrich_bulk_domains(
    leads: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Enrich multiple leads with Prospeo (search → bulk enrich).

    Returns ``{domain: contact_dict}`` for domains where a verified email was
    found. Matches the shape ``apollo_enrich_leads`` returns.
    """
    if not _configured() or not leads:
        return {}

    needs_email = [ld for ld in leads if not ld.get("_email_found")]
    if not needs_email:
        return {}

    out: dict[str, dict[str, Any]] = {}
    sem = asyncio.Semaphore(10)

    async def _enrich_one(lead: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        async with sem:
            domain = (lead.get("domain") or "").strip().lower()
            if not domain:
                return "", None
            contact_name = (lead.get("contact_name") or "").strip()
            vertical = (lead.get("vertical") or "dental").strip()
            company_name = (lead.get("business_name") or lead.get("company_name") or "").strip()
            hit = await enrich_single_domain(
                domain=domain,
                vertical=vertical,
                company_name=company_name,
                contact_name=contact_name,
            )
            return domain, hit

    results = await asyncio.gather(*[_enrich_one(ld) for ld in needs_email])
    for domain, hit in results:
        if domain and hit and hit.get("email"):
            out[domain] = hit

    logger.info("Prospeo bulk enrichment: found contacts for %d/%d leads", len(out), len(needs_email))
    return out


# ── Response parsing helpers ─────────────────────────────────────────────


def _extract_contact(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract contact from enrich-person response.

    Prospeo returns ``email`` and ``mobile`` as nested dicts::

        "email": {"status": "VERIFIED", "email": "jane@example.com", ...}
        "mobile": {"mobile": "+15551234567", ...}
    """
    person = body.get("person") or {}
    if not person:
        return None

    # email may be a dict {"email": "...", "status": "VERIFIED"} or a string
    raw_email = person.get("email") or ""
    if isinstance(raw_email, dict):
        email = (raw_email.get("email") or "").strip().lower()
    else:
        email = str(raw_email).strip().lower()
    if not email or "@" not in email:
        return None

    # mobile may be a dict {"mobile": "+1...", ...} or a string
    raw_mobile = person.get("mobile") or ""
    if isinstance(raw_mobile, dict):
        phone = (raw_mobile.get("mobile") or "").strip()
    else:
        phone = str(raw_mobile).strip()

    return {
        "email": email,
        "first_name": (person.get("first_name") or "").strip(),
        "last_name": (person.get("last_name") or "").strip(),
        "title": (person.get("current_job_title") or person.get("title") or "").strip(),
        "phone": phone,
        "linkedin_url": (person.get("linkedin_url") or "").strip(),
        "source": "prospeo",
    }
