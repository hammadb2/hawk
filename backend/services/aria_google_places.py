"""Google Places (New) lead discovery — replaces Apify Actor 1 for Google Maps.

Calls ``https://places.googleapis.com/v1/places:searchText`` with a Pro-tier
FieldMask (``id``, ``displayName``, ``websiteUri``, ``formattedAddress``,
``phone``, ``rating``, ``userRatingCount``, ``addressComponents``, ``types``).
Pro SKU costs USD 17 per 1 000 places and is covered by Google Maps Platform's
USD 200/month free credit for the nightly cadence used here (~1 000
places/night ≈ USD 17/month → free).

Returns lead dicts in the same shape as ``aria_apify_scraper._map_gmaps_result``
so the rest of the pipeline (Apify LinkedIn / Leads Finder / Website Crawler
enrichment, ZeroBounce, Hawk scan, OpenAI personalization) runs unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Iterable

import httpx

from services.aria_apify_scraper import (
    CITIES,
    VERTICALS,
    VERTICAL_QUERIES,
    _int_env,
    _normalize_domain,
    score_lead,
)

logger = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Keep this FieldMask aligned with the Pro SKU so we never accidentally pull
# Enterprise fields (reviews, opening hours) that would double the per-place
# price. Anything past ``userRatingCount`` lives in the Essentials SKU already.
PLACES_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.websiteUri",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "places.addressComponents",
        "places.types",
    ]
)

GENERIC_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "linkedin.com",
    "yelp.com",
    "yellowpages.com",
}

GOOGLE_PLACES_CONCURRENCY = _int_env("GOOGLE_PLACES_CONCURRENCY", 8)
GOOGLE_PLACES_PAGE_SIZE = _int_env("GOOGLE_PLACES_PAGE_SIZE", 20)


def _address_component(components: list[dict[str, Any]], type_: str) -> str:
    for c in components or []:
        types = c.get("types") or []
        if type_ in types:
            return (c.get("shortText") or c.get("longText") or "").strip()
    return ""


def _map_place_to_lead(
    place: dict[str, Any], vertical: str, city: str
) -> dict[str, Any] | None:
    name_obj = place.get("displayName") or {}
    if isinstance(name_obj, dict):
        name = (name_obj.get("text") or "").strip()
    else:
        name = str(name_obj).strip()
    if not name:
        return None

    website = (place.get("websiteUri") or "").strip()
    if not website:
        return None
    domain = _normalize_domain(website)
    if not domain or domain in GENERIC_DOMAINS:
        return None

    address = (place.get("formattedAddress") or "").strip()
    components = place.get("addressComponents") or []
    result_city = _address_component(components, "locality") or city
    province = _address_component(components, "administrative_area_level_1")

    phone = (
        place.get("internationalPhoneNumber")
        or place.get("nationalPhoneNumber")
        or ""
    ).strip()

    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    place_id = place.get("id") or ""

    return {
        "business_name": name,
        "domain": domain,
        "address": address,
        "city": result_city,
        "province": province,
        "vertical": vertical,
        "google_rating": float(rating) if rating is not None else None,
        "review_count": int(review_count) if review_count is not None else None,
        "google_place_id": str(place_id),
        "phone": phone,
        "emails_from_website": [],
        "status": "pending",
    }


async def _search_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    api_key: str,
    vertical: str,
    city: str,
) -> list[dict[str, Any]]:
    """One ``searchText`` call for a single city × vertical combination."""
    query = VERTICAL_QUERIES[vertical].format(city=city)
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": PLACES_FIELD_MASK,
    }
    body: dict[str, Any] = {
        "textQuery": query,
        "pageSize": GOOGLE_PLACES_PAGE_SIZE,
        "languageCode": "en",
        "regionCode": "CA",
    }

    async with sem:
        try:
            r = await client.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=60.0)
        except httpx.HTTPError as exc:
            logger.warning("Google Places request failed %s/%s: %s", vertical, city, exc)
            return []

    if r.status_code >= 400:
        logger.warning(
            "Google Places error %s/%s status=%d body=%s",
            vertical,
            city,
            r.status_code,
            r.text[:400],
        )
        return []

    try:
        data = r.json() or {}
    except ValueError:
        logger.warning("Google Places returned non-JSON for %s/%s", vertical, city)
        return []

    places = data.get("places") or []
    leads: list[dict[str, Any]] = []
    for place in places:
        lead = _map_place_to_lead(place, vertical, city)
        if lead:
            leads.append(lead)

    # Deduplicate by domain within this single query (occasionally Places returns
    # the same business under several categories).
    by_domain: dict[str, dict[str, Any]] = {}
    for lead in leads:
        d = lead["domain"]
        prev = by_domain.get(d)
        if prev is None or int(lead.get("review_count") or 0) > int(prev.get("review_count") or 0):
            by_domain[d] = lead
    merged = list(by_domain.values())

    logger.info(
        "Google Places %s/%s: %d raw → %d with domain → %d deduped",
        vertical,
        city,
        len(places),
        len(leads),
        len(merged),
    )
    return merged


async def discover_leads(
    cities: Iterable[str] | None = None,
    verticals: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Run Google Places searchText across all city × vertical combinations.

    Returns a deduplicated list of lead dicts shaped identically to the output
    of ``aria_apify_scraper.run_actor1_google_maps`` — so the downstream
    enrichment / verify / scan / personalize / store steps work unchanged.
    """
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        logger.error("GOOGLE_PLACES_API_KEY not configured — cannot run Google Places discovery")
        return []

    city_list = list(cities) if cities else list(CITIES)
    vertical_list = list(verticals) if verticals else list(VERTICALS)

    sem = asyncio.Semaphore(GOOGLE_PLACES_CONCURRENCY)
    all_leads: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        tasks = [
            _search_one(client, sem, api_key, vertical, city)
            for vertical in vertical_list
            for city in city_list
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.warning("Google Places task failed: %s", result)
            continue
        all_leads.extend(result)

    # Global dedup by domain, keep highest-scored occurrence.
    domain_map: dict[str, dict[str, Any]] = {}
    for lead in all_leads:
        d = lead["domain"]
        lead["lead_score"] = score_lead(lead)
        if d not in domain_map or lead["lead_score"] > domain_map[d].get("lead_score", 0):
            domain_map[d] = lead

    deduped = list(domain_map.values())
    logger.info(
        "Google Places discovery complete: %d raw → %d unique leads from %d cities × %d verticals",
        len(all_leads),
        len(deduped),
        len(city_list),
        len(vertical_list),
    )
    return deduped
