"""
Google Places API scraper for ARIA nightly pipeline.

Discovers dental clinics, law firms, and accounting / CPA practices across the 30 US
metros targeted by ``aria_apify_scraper.CITIES``. Runs all city queries in parallel
using asyncio.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from config import GOOGLE_PLACES_API_KEY

logger = logging.getLogger(__name__)

# Google Places API (New) endpoints
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Vertical → Google Places search queries
VERTICAL_QUERIES: dict[str, list[str]] = {
    "dental": ["dental clinic", "dentist office", "dental practice"],
    "legal": ["law firm", "lawyer office", "legal practice"],
    "accounting": ["accounting firm", "CPA firm", "accountant office"],
}

# Province mapping from Google Places address components
PROVINCE_MAP: dict[str, str] = {
    "alberta": "AB",
    "british columbia": "BC",
    "manitoba": "MB",
    "new brunswick": "NB",
    "newfoundland and labrador": "NL",
    "nova scotia": "NS",
    "ontario": "ON",
    "prince edward island": "PE",
    "quebec": "QC",
    "saskatchewan": "SK",
    "northwest territories": "NT",
    "nunavut": "NU",
    "yukon": "YT",
}


def _normalize_domain(raw: str) -> str:
    """Extract clean domain from a website URL."""
    d = (raw or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    d = d.split("/")[0].split("?")[0].strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def _extract_province(address_components: list[dict[str, Any]]) -> str:
    """Extract province abbreviation from Google Places address components."""
    for comp in address_components:
        types = comp.get("types") or []
        if "administrative_area_level_1" in types:
            long_name = (comp.get("longText") or "").lower()
            short_name = comp.get("shortText") or ""
            if short_name and len(short_name) == 2:
                return short_name.upper()
            return PROVINCE_MAP.get(long_name, short_name.upper())
    return ""


def _map_place_to_lead(place: dict[str, Any], vertical: str) -> dict[str, Any] | None:
    """Map a Google Places result to an aria_lead_inventory row."""
    name = (place.get("displayName") or {}).get("text") or ""
    if not name:
        return None

    # Extract website domain
    website = place.get("websiteUri") or ""
    domain = _normalize_domain(website)
    if not domain:
        return None

    # Extract address
    formatted_address = place.get("formattedAddress") or ""
    address_components = place.get("addressComponents") or []

    # Extract city from address components
    city = ""
    for comp in address_components:
        types = comp.get("types") or []
        if "locality" in types:
            city = comp.get("longText") or ""
            break

    province = _extract_province(address_components)

    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    place_id = place.get("id") or ""

    return {
        "business_name": name.strip(),
        "domain": domain,
        "address": formatted_address,
        "city": city,
        "province": province,
        "vertical": vertical,
        "google_rating": float(rating) if rating is not None else None,
        "review_count": int(review_count) if review_count is not None else None,
        "google_place_id": place_id,
        "status": "pending",
    }


async def _search_places_for_query(
    client: httpx.AsyncClient,
    query: str,
    city: str,
    semaphore: asyncio.Semaphore,
) -> list[dict[str, Any]]:
    """Run a single Google Places text search query."""
    async with semaphore:
        results: list[dict[str, Any]] = []
        # Pair each city with its US state using ``CITY_STATE`` from
        # ``aria_apify_scraper`` so Google Places disambiguates metros like
        # ``Portland`` (OR vs ME) and ``Columbus`` (OH vs GA). Falls back to
        # a bare ``"... in {city}, USA"`` query if the mapping is missing
        # (safe because ``regionCode="US"`` is already set on the request).
        from services.aria_apify_scraper import CITY_STATE as _CITY_STATE

        _entry = _CITY_STATE.get((city or "").strip().lower())
        if _entry:
            _state_full, _ = _entry
            text_query = f"{query} in {city}, {_state_full}, USA"
        else:
            text_query = f"{query} in {city}, USA"

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.addressComponents,places.websiteUri,"
                "places.rating,places.userRatingCount"
            ),
        }

        try:
            # First page
            body: dict[str, Any] = {
                "textQuery": text_query,
                "languageCode": "en",
                # US market: bias Google Places results to the US to match
                # the US-only discovery targets.
                "regionCode": "US",
                "pageSize": 20,
            }
            r = await client.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=30.0)
            if r.status_code >= 400:
                logger.warning("Places search failed query=%r status=%d body=%s", text_query, r.status_code, r.text[:300])
                return results

            data = r.json()
            places = data.get("places") or []
            results.extend(places)

            # Paginate (up to 3 pages = 60 results per query)
            for _ in range(2):
                next_token = data.get("nextPageToken")
                if not next_token:
                    break
                body["pageToken"] = next_token
                await asyncio.sleep(0.5)  # Rate limit courtesy
                r = await client.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=30.0)
                if r.status_code >= 400:
                    break
                data = r.json()
                places = data.get("places") or []
                results.extend(places)

        except Exception as exc:
            logger.warning("Places search error query=%r: %s", text_query, exc)

        return results


async def scrape_vertical_city(
    client: httpx.AsyncClient,
    vertical: str,
    city: str,
    semaphore: asyncio.Semaphore,
) -> list[dict[str, Any]]:
    """Scrape all queries for a single vertical+city combination."""
    queries = VERTICAL_QUERIES.get(vertical, VERTICAL_QUERIES["dental"])
    all_places: list[dict[str, Any]] = []

    for query in queries:
        places = await _search_places_for_query(client, query, city, semaphore)
        all_places.extend(places)

    # Deduplicate by place_id
    seen_ids: set[str] = set()
    unique: list[dict[str, Any]] = []
    for place in all_places:
        pid = place.get("id") or ""
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            unique.append(place)

    # Map to lead format
    leads: list[dict[str, Any]] = []
    for place in unique:
        lead = _map_place_to_lead(place, vertical)
        if lead:
            leads.append(lead)

    return leads


async def scrape_all_verticals(
    cities: list[str],
    verticals: list[str] | None = None,
    concurrency: int = 10,
) -> list[dict[str, Any]]:
    """
    Scrape Google Places for all verticals across all cities.

    Args:
        cities: List of US cities to scrape (see ``aria_apify_scraper.CITIES``
            for the canonical 30-metro target list)
        verticals: List of verticals (default: dental, legal, accounting)
        concurrency: Max concurrent API requests

    Returns:
        List of lead dicts ready for aria_lead_inventory insertion
    """
    if not GOOGLE_PLACES_API_KEY:
        logger.error("GOOGLE_PLACES_API_KEY not configured — skipping Places scrape")
        return []

    if verticals is None:
        verticals = list(VERTICAL_QUERIES.keys())

    semaphore = asyncio.Semaphore(concurrency)
    all_leads: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = []
        for vertical in verticals:
            for city in cities:
                tasks.append(scrape_vertical_city(client, vertical, city, semaphore))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Places scrape task failed: %s", result)
                continue
            all_leads.extend(result)

    # Global dedup by domain (keep first occurrence = highest quality)
    seen_domains: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for lead in all_leads:
        domain = lead["domain"]
        if domain not in seen_domains:
            seen_domains.add(domain)
            deduped.append(lead)

    logger.info("Places scrape complete: %d leads from %d cities x %d verticals", len(deduped), len(cities), len(verticals))
    return deduped


def score_lead(lead: dict[str, Any]) -> int:
    """
    Score a lead from Google Places data (pre-enrichment).

    Scoring rules:
    - Rating > 4.0: +2
    - Review count > 50: +2
    - Review count > 200: +3 (replaces the +2)
    - Website present: +1
    - Major city: +1
    """
    score = 0
    rating = lead.get("google_rating")
    if rating is not None and float(rating) > 4.0:
        score += 2

    reviews = lead.get("review_count")
    if reviews is not None:
        if int(reviews) > 200:
            score += 3
        elif int(reviews) > 50:
            score += 2

    if lead.get("domain"):
        score += 1

    major_cities = {
        "toronto", "vancouver", "calgary", "edmonton", "ottawa", "montreal",
        "winnipeg", "halifax", "hamilton", "mississauga", "brampton",
    }
    city = (lead.get("city") or "").lower()
    if city in major_cities:
        score += 1

    return score
