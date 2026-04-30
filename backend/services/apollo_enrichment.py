"""Apollo.io contact enrichment — replaces Apify actors 2/3/4.

Given a prospect (domain + vertical), find a decision-maker contact's name,
email, title, phone, and LinkedIn URL. Uses Apollo's ``mixed_people/api_search``
endpoint (formerly ``mixed_people/search`` — deprecated for API callers in
early 2026) filtered by ``q_organization_domains_list`` + vertical-specific
titles. Emails are then unlocked via ``people/bulk_match`` since the search
endpoint itself does not return email addresses.

Also provides ``apollo_people_topup`` for hybrid discovery: pull verified
contacts directly from Apollo when Google Places volume is below the daily
target (currently 2 000 contacts/day; see :mod:`services.apollo_discovery`).

Design notes:
- Per Apollo docs, ``mixed_people/api_search`` does **not** consume credits.
  Only the email-unlock (``people/bulk_match``) burns credits, so credit
  tracking now increments solely around bulk-match.
- Credits are tracked per-day in ``crm_settings.apollo_credits_used_today`` and
  ``crm_settings.apollo_credits_used_date`` so we can enforce
  ``apollo_daily_credit_cap`` without hitting Apollo's rate limits.
- Returns ``None`` when no verified contact is found so the post-scan pipeline
  soft-drops the prospect consistently with the previous Apify-based flow.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any

import httpx

from config import APOLLO_API_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

APOLLO_BASE = os.environ.get("APOLLO_API_BASE", "https://api.apollo.io/api/v1").rstrip("/")

# Vertical → decision-maker titles Apollo should filter on.
VERTICAL_TITLES: dict[str, list[str]] = {
    "dental": [
        "dentist",
        "owner",
        "principal dentist",
        "managing dentist",
        "practice owner",
        "clinic owner",
        "dental director",
        "practice manager",
    ],
    "legal": [
        "managing partner",
        "partner",
        "owner",
        "principal",
        "founder",
        "lawyer",
        "solicitor",
        "attorney",
    ],
    "accounting": [
        "managing partner",
        "partner",
        "owner",
        "principal",
        "cpa",
        "chartered accountant",
        "practice manager",
    ],
    "medical": [
        "physician",
        "doctor",
        "owner",
        "medical director",
        "practice owner",
        "practice manager",
        "office manager",
    ],
    "optometry": [
        "optometrist",
        "owner",
        "doctor of optometry",
        "od",
        "practice owner",
        "practice manager",
    ],
    "chiropractic": [
        "chiropractor",
        "owner",
        "doctor of chiropractic",
        "dc",
        "practice owner",
        "clinic director",
    ],
    "physical_therapy": [
        "physical therapist",
        "owner",
        "clinic owner",
        "clinic director",
        "practice manager",
        "doctor of physical therapy",
        "dpt",
    ],
    "mental_health": [
        "therapist",
        "psychologist",
        "psychiatrist",
        "owner",
        "clinical director",
        "practice owner",
        "practice manager",
    ],
    "pharmacy": [
        "pharmacist",
        "owner",
        "pharmacy owner",
        "pharmacist in charge",
        "managing pharmacist",
        "rph",
    ],
    "real_estate": [
        "broker",
        "managing broker",
        "owner",
        "principal broker",
        "designated broker",
        "real estate agent",
        "realtor",
    ],
    "financial_advisor": [
        "financial advisor",
        "wealth advisor",
        "owner",
        "principal",
        "managing director",
        "investment advisor",
        "financial planner",
        "cfp",
    ],
    "insurance": [
        "owner",
        "principal",
        "agency owner",
        "insurance agent",
        "agent principal",
        "managing partner",
        "broker",
    ],
    "mortgage": [
        "owner",
        "broker",
        "mortgage broker",
        "principal",
        "loan officer",
        "branch manager",
        "managing partner",
    ],
    "hr_payroll": [
        "owner",
        "principal",
        "managing partner",
        "founder",
        "ceo",
        "president",
        "operations manager",
    ],
}


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _apollo_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY,
    }


def _configured() -> bool:
    return bool(APOLLO_API_KEY and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


# ── Credit tracking ──────────────────────────────────────────────────────


def _fetch_setting(key: str, default: str = "") -> str:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
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
        logger.warning("apollo fetch setting %s failed: %s", key, exc)
    return default


def _upsert_setting(key: str, value: str) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"key": key, "value": value},
            timeout=10.0,
        )
    except Exception as exc:
        logger.warning("apollo upsert setting %s failed: %s", key, exc)


def _reset_daily_counter_if_needed() -> int:
    """Reset the daily credit counter when the UTC date rolls over. Returns used today."""
    today = date.today().isoformat()
    stored_date = _fetch_setting("apollo_credits_used_date", "")
    if stored_date != today:
        _upsert_setting("apollo_credits_used_date", today)
        _upsert_setting("apollo_credits_used_today", "0")
        return 0
    try:
        return int(_fetch_setting("apollo_credits_used_today", "0") or 0)
    except ValueError:
        return 0


def _increment_credits(n: int = 1) -> None:
    used = _reset_daily_counter_if_needed()
    _upsert_setting("apollo_credits_used_today", str(used + max(1, n)))


def credits_remaining_today() -> int:
    """How many Apollo credits can still be used today given the configured cap."""
    try:
        cap = int(_fetch_setting("apollo_daily_credit_cap", "2500"))
    except ValueError:
        cap = 2500
    return max(0, cap - _reset_daily_counter_if_needed())


# ── People search ────────────────────────────────────────────────────────


def _normalize_domain(raw: str) -> str:
    d = (raw or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    d = d.split("/")[0].split("?")[0].strip()
    if "@" in d:
        d = d.split("@")[-1]
    if d.startswith("www."):
        d = d[4:]
    return d


def _location_strings(city: str | None, region: str | None) -> list[str]:
    """Build Apollo ``person_locations`` strings for US metros.

    ``region`` is the US state (full name or 2-letter abbreviation). The
    ``province`` parameter name is preserved by callers historically — we
    accept it under ``region`` now but keep behaviour backward-compatible.
    """
    out: list[str] = []
    city = (city or "").strip()
    region = (region or "").strip()
    if city and region:
        out.append(f"{city}, {region}, USA")
    if city:
        out.append(f"{city}, USA")
    if region:
        out.append(f"{region}, USA")
    return out or ["United States"]


def _select_person(people: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the best decision-maker record. Prefer verified email + earlier title in list."""
    if not people:
        return None
    scored: list[tuple[int, dict[str, Any]]] = []
    for p in people:
        if not isinstance(p, dict):
            continue
        email = (p.get("email") or p.get("primary_email") or "").strip()
        if not email or "@" not in email or "email_not_unlocked" in email.lower():
            continue
        status = str(p.get("email_status") or "").lower()
        score = 0
        if status == "verified":
            score += 10
        elif status == "likely to engage":
            score += 5
        if (p.get("first_name") or "").strip():
            score += 2
        if (p.get("last_name") or "").strip():
            score += 2
        scored.append((score, p))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


async def _apollo_bulk_match_unlock(
    people: list[dict[str, Any]],
    *,
    client: httpx.AsyncClient,
) -> None:
    """Reveal obfuscated emails on ``people`` rows in place via ``people/bulk_match``.

    Apollo's ``mixed_people/api_search`` endpoint returns person records but keeps
    the actual ``email`` field locked (empty or ``email_not_unlocked@…``) until
    a separate unlock call is made. Without this step the post-scan pipeline
    can never produce a usable contact and soft-drops every prospect.

    Mutates each person dict so ``person["email"]`` (and ``primary_email``)
    holds the revealed address when Apollo has it. Chunks at 10 ids per call
    to match Apollo's bulk_match limit; each chunk counts as ``len(chunk)``
    credits in our daily counter.
    """
    need = [
        p for p in people
        if isinstance(p, dict)
        and p.get("id")
        and (
            not (p.get("email") or p.get("primary_email"))
            or "email_not_unlocked" in str(p.get("email") or p.get("primary_email") or "").lower()
        )
    ]
    for i in range(0, len(need), 10):
        if credits_remaining_today() <= 0:
            logger.warning("Apollo daily credit cap reached — stopping email unlock sweep")
            return
        chunk = need[i : i + 10]
        ids = [str(p["id"]) for p in chunk]
        payload = {
            "reveal_personal_emails": True,
            "details": [{"id": pid} for pid in ids],
        }
        try:
            r = await client.post(
                f"{APOLLO_BASE}/people/bulk_match",
                headers=_apollo_headers(),
                json=payload,
                timeout=45.0,
            )
        except Exception as exc:
            logger.warning("Apollo bulk_match error ids=%d: %s", len(ids), exc)
            continue
        if r.status_code >= 400:
            logger.warning(
                "Apollo bulk_match HTTP %s ids=%d body=%s",
                r.status_code, len(ids), r.text[:300],
            )
            continue
        _increment_credits(len(chunk))
        try:
            data = r.json() or {}
        except Exception:
            continue
        matches = data.get("matches") or data.get("people") or []
        by_id: dict[str, dict[str, Any]] = {}
        for m in matches:
            if isinstance(m, dict) and m.get("id"):
                by_id[str(m["id"])] = m
        for p in chunk:
            pid = str(p.get("id") or "")
            m = by_id.get(pid)
            if not m:
                continue
            em = str(m.get("email") or m.get("primary_email") or "").strip()
            if em and "@" in em and "email_not_unlocked" not in em.lower():
                p["email"] = em


async def _apollo_people_search(
    *,
    domain: str | None = None,
    vertical: str,
    city: str | None = None,
    province: str | None = None,
    per_page: int = 10,
    page: int = 1,
    client: httpx.AsyncClient | None = None,
    status_filter: list[str] | None = None,
    titles_override: list[str] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute one ``mixed_people/api_search`` call. Returns raw ``people`` list.

    Uses Apollo's current API-only search endpoint. The legacy
    ``mixed_people/search`` endpoint was deprecated for API callers in 2026
    and now returns HTTP 422 with a deprecation pointer. ``status_filter`` +
    ``titles_override`` let callers progressively relax the query when the
    strict pass returns nothing.

    Note: per Apollo, ``api_search`` does not consume search credits. Email
    unlock via ``people/bulk_match`` still does; that's tracked separately.
    """
    body: dict[str, Any] = {
        "page": page,
        "per_page": min(100, max(1, per_page)),
        "person_titles": titles_override
        or VERTICAL_TITLES.get(vertical, VERTICAL_TITLES["dental"]),
        "contact_email_status": status_filter
        or ["verified", "likely to engage"],
    }
    if domain:
        # api_search expects ``q_organization_domains_list`` as an array.
        # (Legacy ``q_organization_domains`` was a newline-delimited string.)
        body["q_organization_domains_list"] = [domain]
    if city or province:
        body["person_locations"] = _location_strings(city, province)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=45.0)
    try:
        r = await client.post(
            f"{APOLLO_BASE}/mixed_people/api_search",
            headers=_apollo_headers(),
            json=body,
            timeout=45.0,
        )
        if diagnostics is not None:
            diagnostics.setdefault("search_calls", []).append(
                {
                    "domain": domain,
                    "vertical": vertical,
                    "city": city,
                    "province": province,
                    "status_filter": body["contact_email_status"],
                    "http_status": r.status_code,
                    "body_snippet": r.text[:300] if r.status_code >= 400 else "",
                }
            )
        if r.status_code >= 400:
            logger.warning(
                "Apollo mixed_people/api_search HTTP %s domain=%s body=%s",
                r.status_code, domain, r.text[:300],
            )
            return []
        # api_search is credit-free per Apollo docs; only bulk_match burns credits.
        data = r.json() or {}
        people = list(data.get("people") or data.get("contacts") or [])
        if diagnostics is not None:
            diagnostics["search_calls"][-1]["people_count"] = len(people)
            # Distribution of email_status values so we can tell whether the
            # filter bucket is actually the bottleneck.
            statuses: dict[str, int] = {}
            for p in people:
                if isinstance(p, dict):
                    s = str(p.get("email_status") or "").strip().lower() or "—"
                    statuses[s] = statuses.get(s, 0) + 1
            diagnostics["search_calls"][-1]["email_statuses"] = statuses
        return people
    except Exception as exc:
        logger.warning("Apollo mixed_people/api_search error domain=%s: %s", domain, exc)
        if diagnostics is not None:
            diagnostics.setdefault("search_calls", []).append(
                {"domain": domain, "error": str(exc)[:300]}
            )
        return []
    finally:
        if own_client and client is not None:
            await client.aclose()


# Progressive relaxation ladder. Each pass is tried in order until one
# produces people we can unlock. Valid ``contact_email_status`` values per
# Apollo docs: verified, unverified, likely to engage, unavailable. Keeps the
# default verified-only gate for the common case while still recovering
# domains Apollo has indexed at lower confidence.
_STATUS_LADDER: list[list[str]] = [
    ["verified"],
    ["verified", "likely to engage"],
    ["verified", "likely to engage", "unverified"],
]


async def enrich_single_domain_verbose(
    *,
    domain: str,
    vertical: str,
    company_name: str = "",
    city: str | None = None,
    province: str | None = None,
) -> dict[str, Any]:
    """Apollo enrichment with full diagnostics.

    Always returns a dict shaped as::

        {
            "found": bool,
            "reason": "…",         # when found=False
            "contact": {...},      # when found=True, matches the legacy shape
            "diagnostics": {...},  # per-call HTTP status + people counts + statuses
        }

    The diagnostic payload is what the ``/api/crm/cron/apollo-diagnose``
    endpoint surfaces. ``enrich_single_domain`` wraps this function for
    backwards compatibility.
    """
    diag: dict[str, Any] = {"search_calls": []}

    if not _configured():
        return {"found": False, "reason": "apollo_not_configured", "diagnostics": diag}
    norm_domain = _normalize_domain(domain)
    if not norm_domain:
        return {"found": False, "reason": "empty_domain", "diagnostics": diag}
    if credits_remaining_today() <= 0:
        logger.warning(
            "Apollo daily credit cap reached — skipping enrichment for %s", norm_domain
        )
        return {"found": False, "reason": "daily_credit_cap_reached", "diagnostics": diag}

    people: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=45.0) as client:
        # Pass 1 → 3: domain-anchored search, progressively relaxed email-status
        # filter. Stop the moment we get a hit.
        for status_filter in _STATUS_LADDER:
            if credits_remaining_today() <= 0:
                break
            people = await _apollo_people_search(
                domain=norm_domain,
                vertical=vertical,
                client=client,
                per_page=10,
                status_filter=status_filter,
                diagnostics=diag,
            )
            if people:
                break

        # Pass 4: geo + company-name fallback for businesses Apollo hasn't
        # indexed by domain.
        if not people and company_name and city and credits_remaining_today() > 0:
            people = await _apollo_people_search(
                vertical=vertical,
                city=city,
                province=province,
                client=client,
                per_page=25,
                status_filter=_STATUS_LADDER[-1],
                diagnostics=diag,
            )

        if people:
            await _apollo_bulk_match_unlock(people, client=client)

    if not people:
        return {"found": False, "reason": "no_people_returned", "diagnostics": diag}

    person = _select_person(people)
    if not person:
        # Count how many had locked emails so the reason is actionable.
        locked = sum(
            1 for p in people
            if isinstance(p, dict)
            and "email_not_unlocked" in str(
                p.get("email") or p.get("primary_email") or ""
            ).lower()
        )
        diag["people_returned"] = len(people)
        diag["people_locked_email"] = locked
        return {
            "found": False,
            "reason": "no_verified_contact_after_unlock",
            "diagnostics": diag,
        }

    email = str(person.get("email") or person.get("primary_email") or "").strip().lower()
    if not email or "@" not in email:
        return {
            "found": False,
            "reason": "person_selected_but_email_missing",
            "diagnostics": diag,
        }

    contact = {
        "email": email,
        "first_name": str(person.get("first_name") or "").strip(),
        "last_name": str(person.get("last_name") or "").strip(),
        "title": str(person.get("title") or "").strip(),
        "phone": str(
            person.get("phone")
            or person.get("sanitized_phone")
            or person.get("mobile_phone")
            or ""
        ).strip(),
        "linkedin_url": str(person.get("linkedin_url") or "").strip(),
        "apollo_person_id": str(person.get("id") or "").strip(),
        "source": "apollo",
    }
    diag["people_returned"] = len(people)
    return {"found": True, "contact": contact, "diagnostics": diag}


async def enrich_single_domain(
    *,
    domain: str,
    vertical: str,
    company_name: str = "",
    city: str | None = None,
    province: str | None = None,
) -> dict[str, Any] | None:
    """Find a verified decision-maker contact for a single domain via Apollo.

    Returns a dict matching the shape ``aria_post_scan_pipeline`` expects::

        {
            "email": "jane@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "title": "Managing Partner",
            "phone": "+15551234567",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "source": "apollo",
        }

    ``None`` when no verified contact is found or Apollo is not configured.
    Soft budget guard: if today's credit counter has already hit the cap this
    function returns ``None`` rather than making another call. Backed by
    :func:`enrich_single_domain_verbose` for the diagnostics.
    """
    res = await enrich_single_domain_verbose(
        domain=domain,
        vertical=vertical,
        company_name=company_name,
        city=city,
        province=province,
    )
    if not res.get("found"):
        logger.info(
            "Apollo enrich blank domain=%s reason=%s",
            domain,
            res.get("reason"),
        )
        return None
    return res.get("contact") or None


def enrich_single_domain_sync(
    *,
    domain: str,
    vertical: str,
    company_name: str = "",
    city: str | None = None,
    province: str | None = None,
) -> dict[str, Any] | None:
    """Blocking helper for non-async callers (cron jobs, background threads)."""
    try:
        return asyncio.run(
            enrich_single_domain(
                domain=domain,
                vertical=vertical,
                company_name=company_name,
                city=city,
                province=province,
            )
        )
    except RuntimeError:
        # Already inside an event loop — caller should use the async variant.
        return None


# ── Hybrid discovery top-up ──────────────────────────────────────────────


async def apollo_people_topup(
    *,
    vertical: str,
    locations: list[str],
    batch_size: int,
) -> list[dict[str, Any]]:
    """Pull verified decision-maker contacts directly from Apollo.

    Returns leads in the ``aria_google_places._map_place_to_lead`` shape so the
    rest of the discovery pipeline (dedup, upsert, post-scan) treats them the
    same as Google Places results.
    """
    if not _configured() or batch_size <= 0 or credits_remaining_today() <= 0:
        return []
    results: list[dict[str, Any]] = []
    seen_email: set[str] = set()
    seen_domain: set[str] = set()

    async with httpx.AsyncClient(timeout=45.0) as client:
        for loc in locations:
            if len(results) >= batch_size or credits_remaining_today() <= 0:
                break
            city, province = _parse_location(loc)
            page = 1
            while len(results) < batch_size and page <= 4:
                people = await _apollo_people_search(
                    vertical=vertical,
                    city=city,
                    province=province,
                    per_page=min(100, batch_size - len(results)),
                    page=page,
                    client=client,
                )
                if not people:
                    break
                # Reveal emails before filtering — search alone returns them locked.
                await _apollo_bulk_match_unlock(people, client=client)
                for p in people:
                    if not isinstance(p, dict):
                        continue
                    email = (p.get("email") or p.get("primary_email") or "").strip().lower()
                    if (
                        not email
                        or "@" not in email
                        or "email_not_unlocked" in email
                        or email in seen_email
                    ):
                        continue
                    org = p.get("organization") or {}
                    if isinstance(org, str):
                        org = {}
                    website = (
                        org.get("website_url")
                        or org.get("primary_domain")
                        or p.get("organization_website_url")
                        or ""
                    )
                    domain = _normalize_domain(str(website)) if website else ""
                    if not domain:
                        domain = _normalize_domain(email.split("@")[-1])
                    if not domain or domain in seen_domain:
                        continue
                    seen_email.add(email)
                    seen_domain.add(domain)
                    results.append(
                        {
                            "business_name": str(org.get("name") or "").strip(),
                            "company_name": str(org.get("name") or "").strip(),
                            "domain": domain,
                            "vertical": vertical,
                            "industry": vertical,
                            "city": city or str(p.get("city") or "").strip(),
                            "province": province or str(p.get("state") or "").strip(),
                            "phone": str(
                                p.get("phone")
                                or p.get("sanitized_phone")
                                or org.get("phone")
                                or ""
                            ).strip(),
                            "google_rating": None,
                            "review_count": None,
                            "contact_email": email,
                            "contact_name": f"{p.get('first_name', '') or ''} {p.get('last_name', '') or ''}".strip(),
                            "contact_title": str(p.get("title") or "").strip(),
                            "email_finder": "apollo",
                            "lead_score": 1,
                            "status": "pending",
                        }
                    )
                    if len(results) >= batch_size:
                        break
                page += 1

    logger.info("Apollo topup vertical=%s locations=%d → %d leads", vertical, len(locations), len(results))
    return results


def _parse_location(loc: str) -> tuple[str, str]:
    """Parse a "City, Province" string. Tolerates bare city strings."""
    parts = [p.strip() for p in (loc or "").split(",") if p.strip()]
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1])
