"""Apollo.io contact enrichment — replaces Apify actors 2/3/4.

Given a prospect (domain + vertical), find a decision-maker contact's name,
email, title, phone, and LinkedIn URL. Uses Apollo's ``mixed_people/search``
endpoint filtered by ``q_organization_domains`` + vertical-specific titles.

Also provides ``apollo_people_topup`` for hybrid discovery: pull verified
contacts directly from Apollo when Google Places volume is below the daily
target (currently 2 000 contacts/day; see :mod:`services.apollo_discovery`).

Design notes:
- Costs are tracked per-day in ``crm_settings.apollo_credits_used_today`` and
  ``crm_settings.apollo_credits_used_date`` so we can enforce
  ``apollo_daily_credit_cap`` without hitting Apollo's rate limits.
- A single per-prospect enrichment costs 1 search credit + 1 email-unlock
  credit (Apollo business rules change; we count conservatively).
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


def _location_strings(city: str | None, province: str | None) -> list[str]:
    """Build Apollo person_locations strings (city + province/state + country)."""
    out: list[str] = []
    city = (city or "").strip()
    province = (province or "").strip()
    if city and province:
        out.append(f"{city}, {province}, Canada")
    if city:
        out.append(f"{city}, Canada")
    if province:
        out.append(f"{province}, Canada")
    return out or ["Canada"]


def _select_person(people: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the best decision-maker record. Prefer verified email + earlier title in list."""
    if not people:
        return None
    scored: list[tuple[int, dict[str, Any]]] = []
    for p in people:
        if not isinstance(p, dict):
            continue
        email = (p.get("email") or p.get("primary_email") or "").strip()
        if not email or "@" not in email:
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

    Apollo's ``mixed_people/search`` endpoint returns person records but keeps
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
            or "email_not_unlocked" in str(p.get("email") or "").lower()
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
) -> list[dict[str, Any]]:
    """Execute one ``mixed_people/search`` call. Returns raw `people` list."""
    body: dict[str, Any] = {
        "page": page,
        "per_page": min(100, max(1, per_page)),
        "person_titles": VERTICAL_TITLES.get(vertical, VERTICAL_TITLES["dental"]),
        "contact_email_status": ["verified", "likely to engage"],
        "has_email": True,
    }
    if domain:
        body["q_organization_domains"] = domain
    if city or province:
        body["person_locations"] = _location_strings(city, province)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=45.0)
    try:
        r = await client.post(
            f"{APOLLO_BASE}/mixed_people/search",
            headers=_apollo_headers(),
            json=body,
            timeout=45.0,
        )
        if r.status_code >= 400:
            logger.warning(
                "Apollo people/search HTTP %s domain=%s body=%s",
                r.status_code, domain, r.text[:300],
            )
            return []
        _increment_credits(1)
        data = r.json() or {}
        return list(data.get("people") or data.get("contacts") or [])
    except Exception as exc:
        logger.warning("Apollo people/search error domain=%s: %s", domain, exc)
        return []
    finally:
        if own_client and client is not None:
            await client.aclose()


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
    function returns ``None`` rather than making another call.
    """
    if not _configured():
        return None
    domain = _normalize_domain(domain)
    if not domain:
        return None
    if credits_remaining_today() <= 0:
        logger.warning("Apollo daily credit cap reached — skipping enrichment for %s", domain)
        return None

    async with httpx.AsyncClient(timeout=45.0) as client:
        people = await _apollo_people_search(
            domain=domain, vertical=vertical, client=client, per_page=10,
        )
        # If the domain match returned nothing, fall back to company-name + vertical
        # titles in the geography (for businesses Apollo hasn't indexed by
        # domain). Still gated by the daily credit cap above.
        if not people and company_name and city:
            people = await _apollo_people_search(
                vertical=vertical, city=city, province=province, client=client,
                per_page=25,
            )
        # ``mixed_people/search`` returns records with the email field locked
        # (empty or ``email_not_unlocked@…``). Unlock them via bulk_match before
        # selecting, otherwise every prospect soft-drops for "no contact".
        if people:
            await _apollo_bulk_match_unlock(people, client=client)

    person = _select_person(people)
    if not person:
        return None

    email = str(person.get("email") or person.get("primary_email") or "").strip().lower()
    if not email or "@" not in email:
        return None

    return {
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
                    if not email or "@" not in email or email in seen_email:
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
