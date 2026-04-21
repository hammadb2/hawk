"""
ARIA Apify-based lead discovery and email enrichment.

Replaces Google Places + Prospeo + Apollo discovery with four Apify actors:
1. compass/crawler-google-places  — primary lead source (Google Maps scraper)
2. dev_fusion/mass-linkedin-profile-scraper-with-email — decision-maker finder
3. code_crafter/leads-finder — 250M+ contact database fallback
4. apify/website-email-crawler — last-resort website crawl

All 90 city x vertical combinations (30 US metros × 3 verticals) run in
parallel for Actor 1. Actors 2-4 run in async batches of 50 for leads
still missing emails.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import httpx

from config import APOLLO_API_KEY
from services.crm_bool_setting import fetch_crm_bool

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Actor IDs — only Actor 1 (Google Maps) is still used. Actors 2/3/4 have
# been retired in favour of Apollo contact enrichment (cheaper + verified).
ACTOR_GOOGLE_MAPS = "compass/crawler-google-places"


def _actor_path(actor_id: str) -> str:
    """Normalize an Apify actor identifier for use in a REST URL path.

    The REST API identifies actors as ``{username}~{actorName}`` in URL paths.
    A plain ``{username}/{actorName}`` results in a 404 because Apify interprets
    the slash as a path separator.
    """
    return actor_id.replace("/", "~")

# 30 US metros — discovery target set (dental / legal / accounting SMBs).
CITIES: list[str] = [
    "New York", "Los Angeles", "Chicago", "Houston", "Dallas", "Washington DC",
    "Miami", "Phoenix", "Atlanta", "Boston", "San Francisco", "Seattle",
    "Denver", "Minneapolis", "Tampa", "Detroit", "Philadelphia", "San Diego",
    "Portland", "Charlotte", "Orlando", "Austin", "Nashville", "San Antonio",
    "Indianapolis", "Columbus", "Jacksonville", "Las Vegas", "St. Louis",
    "Kansas City",
]

# Map each metro to its US state (used by Google Maps + Apollo location strings).
# Keep keys lowercase-stripped-equal to CITIES entries.
CITY_STATE: dict[str, tuple[str, str]] = {
    "new york": ("New York", "NY"),
    "los angeles": ("California", "CA"),
    "chicago": ("Illinois", "IL"),
    "houston": ("Texas", "TX"),
    "dallas": ("Texas", "TX"),
    "washington dc": ("District of Columbia", "DC"),
    "miami": ("Florida", "FL"),
    "phoenix": ("Arizona", "AZ"),
    "atlanta": ("Georgia", "GA"),
    "boston": ("Massachusetts", "MA"),
    "san francisco": ("California", "CA"),
    "seattle": ("Washington", "WA"),
    "denver": ("Colorado", "CO"),
    "minneapolis": ("Minnesota", "MN"),
    "tampa": ("Florida", "FL"),
    "detroit": ("Michigan", "MI"),
    "philadelphia": ("Pennsylvania", "PA"),
    "san diego": ("California", "CA"),
    "portland": ("Oregon", "OR"),
    "charlotte": ("North Carolina", "NC"),
    "orlando": ("Florida", "FL"),
    "austin": ("Texas", "TX"),
    "nashville": ("Tennessee", "TN"),
    "san antonio": ("Texas", "TX"),
    "indianapolis": ("Indiana", "IN"),
    "columbus": ("Ohio", "OH"),
    "jacksonville": ("Florida", "FL"),
    "las vegas": ("Nevada", "NV"),
    "st. louis": ("Missouri", "MO"),
    "kansas city": ("Missouri", "MO"),
}

# Vertical search queries
VERTICAL_QUERIES: dict[str, str] = {
    "dental": "dental clinics {city}",
    "legal": "law firms {city}",
    "accounting": "accounting practices {city}",
}

VERTICALS = list(VERTICAL_QUERIES.keys())


def canonical_vertical(vertical: str) -> str:
    """Map free-text / LLM vertical labels to a supported pipeline vertical."""
    v = (vertical or "dental").strip().lower()
    if v in VERTICAL_QUERIES:
        return v
    aliases: dict[str, str] = {
        "dentist": "dental",
        "dentists": "dental",
        "dentistry": "dental",
        "dental clinic": "dental",
        "dental_clinic": "dental",
        "law": "legal",
        "lawyer": "legal",
        "lawyers": "legal",
        "attorney": "legal",
        "law firm": "legal",
        "law_firm": "legal",
        "cpa": "accounting",
        "bookkeeping": "accounting",
        "accountant": "accounting",
        "accountants": "accounting",
    }
    if v in aliases:
        return aliases[v]
    for canon in VERTICAL_QUERIES:
        if canon in v or v in canon:
            return canon
    logger.warning("Unknown vertical %r — defaulting to dental", vertical)
    return "dental"


def normalize_city_for_discovery(location: str) -> str:
    """Pick a display city string for Google Maps + dedup, from user/LLM location text."""
    raw = (location or "").strip()
    if not raw:
        return "New York"
    lower = raw.lower()
    for c in CITIES:
        cl = c.lower()
        if cl in lower:
            return c
    first = raw.split(",")[0].strip()
    for c in CITIES:
        if c.lower() == first.lower():
            return c
    return first.title() if first else "New York"


def _state_suffix(city: str) -> str:
    """Return ``", {State}"`` for known US metros, else ``""``."""
    state = CITY_STATE.get((city or "").strip().lower())
    return f", {state[0]}" if state else ""


def search_strings_for_maps(vertical: str, city: str) -> list[str]:
    """Several Google Maps query variants for better recall (one Apify run, deduped strings)."""
    city = (city or "").strip()
    state_suffix = _state_suffix(city)
    primary = VERTICAL_QUERIES[vertical].format(city=city)
    extras: dict[str, list[str]] = {
        "dental": [
            f"dentist {city}",
            f"dental office {city}",
            f"dental practice {city}{state_suffix}",
            f"family dentist {city}",
            f"dentistry {city}",
        ],
        "legal": [
            f"law firm {city}",
            f"lawyers {city}",
            f"law office {city}",
            f"attorney {city}{state_suffix}",
        ],
        "accounting": [
            f"CPA {city}",
            f"accounting firm {city}",
            f"tax preparer {city}",
            f"bookkeeping {city}",
        ],
    }
    out: list[str] = []
    seen: set[str] = set()
    for s in [primary] + extras.get(vertical, []):
        key = " ".join(s.split()).lower()
        if key not in seen:
            seen.add(key)
            out.append(" ".join(s.split()))
    return out[:12]


def _apollo_location_strings(city: str) -> list[str]:
    """Apollo ``person_locations`` variants for a US metro (trial order).

    Emits ``City, State``, ``City, ST`` (abbrev), ``City, State, USA`` and a
    ``City, USA`` tail. Apollo matches any of these so we feed the richer
    variants first and fall back to the loose ``City, USA`` form.
    """
    city = (city or "").strip()
    lc = city.lower()
    locs: list[str] = []
    entry = CITY_STATE.get(lc)
    if entry:
        state_full, state_abbr = entry
        locs.extend(
            [
                f"{city}, {state_full}",
                f"{city}, {state_abbr}",
                f"{city}, {state_full}, USA",
                f"{city}, {state_abbr}, USA",
            ]
        )
    # NYC variant
    if lc == "new york":
        locs.extend([
            "New York City, New York, USA",
            "Manhattan, New York, USA",
            "Brooklyn, New York, USA",
        ])
    # DC variant
    if lc == "washington dc":
        locs.extend(["Washington, DC, USA", "Washington, District of Columbia, USA"])
    tail = f"{city}, USA"
    if tail not in locs:
        locs.append(tail)
    deduped: list[str] = []
    seen = set()
    for x in locs:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            deduped.append(x)
    return deduped


def _apollo_organization_keyword_tags(vertical: str) -> list[str]:
    """Align with aria_pipeline VERTICAL_CONFIG keyword-style tags for mixed_people/search."""
    tags = {
        "dental": ["dental", "dentistry", "dentist", "dental clinic"],
        "legal": ["law firm", "legal services", "lawyer"],
        "accounting": ["accounting", "CPA", "bookkeeping"],
    }
    return tags.get(vertical, tags["dental"])[:5]


def _extract_place_website(item: dict[str, Any]) -> str:
    """Best-effort website URL from Apify compass/crawler-google-places row."""
    for key in ("website", "websiteUrl", "website_url", "url"):
        v = item.get(key)
        if isinstance(v, str) and v.strip() and not v.startswith("tel:"):
            return v.strip()
    nested = item.get("websiteUrls") or item.get("websites") or item.get("links")
    if isinstance(nested, list):
        for entry in nested:
            if isinstance(entry, str) and entry.strip():
                return entry.strip()
            if isinstance(entry, dict):
                for k in ("url", "website", "href", "link"):
                    u = entry.get(k)
                    if isinstance(u, str) and u.strip():
                        return u.strip()
    ws = item.get("scrapeWebsiteData") or item.get("scrapedWebsite")
    if isinstance(ws, dict):
        for k in ("url", "website", "websiteUrl"):
            u = ws.get(k)
            if isinstance(u, str) and u.strip():
                return u.strip()
    return ""


# Major US metros for scoring bonus (lead ranker gives +N for large urban footprint).
MAJOR_CITIES = {
    "new york", "los angeles", "chicago", "houston", "dallas",
    "washington dc", "miami", "phoenix", "atlanta", "boston",
    "san francisco", "seattle", "philadelphia", "san diego",
}

# Polling config (Actor 1 Google Maps only)
APIFY_POLL_INTERVAL = 10  # seconds
APIFY_MAX_WAIT = 900  # 15 minutes max per actor run

# Concurrency + memory tuning to stay inside an Apify plan's memory budget.
# On the FREE plan the total memory across all concurrent actor runs is 8192MB
# and each run defaults to 4096MB, so only 2 can execute at once. Anything over
# that returns HTTP 402 ``actor-memory-limit-exceeded`` and the run silently
# drops. These knobs let the nightly pipeline serialize itself cleanly on free
# and fan out wider on paid plans without code changes.
def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _optional_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return max(128, int(raw))
    except ValueError:
        return None


APIFY_GMAPS_CONCURRENCY = _int_env("APIFY_GMAPS_CONCURRENCY", 2)
APIFY_BATCH_CONCURRENCY = _int_env("APIFY_BATCH_CONCURRENCY", 2)
APIFY_ACTOR_MEMORY_MB = _optional_int_env("APIFY_ACTOR_MEMORY_MB")


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _normalize_domain(raw: str) -> str:
    """Extract clean domain from a website URL."""
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


def score_lead(lead: dict[str, Any]) -> int:
    """Score a lead using Google Places data.

    Scoring:
    - Google rating above 4.0: +2
    - Review count above 50: +2
    - Review count above 200: +3 extra (replaces the +2)
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

    city = (lead.get("city") or "").lower().strip()
    if city in MAJOR_CITIES:
        score += 1

    return score


# ── Apify REST helpers ────────────────────────────────────────────────────


async def _start_actor_run(
    client: httpx.AsyncClient,
    actor_id: str,
    run_input: dict[str, Any],
) -> str | None:
    """Start an Apify actor run. Returns the run ID or None on failure."""
    url = f"{APIFY_BASE}/acts/{_actor_path(actor_id)}/runs"
    params: dict[str, Any] = {"token": os.environ.get("APIFY_API_KEY", "").strip()}
    if APIFY_ACTOR_MEMORY_MB:
        params["memory"] = APIFY_ACTOR_MEMORY_MB
    try:
        r = await client.post(
            url,
            json=run_input,
            params=params,
            timeout=60.0,
        )
        if r.status_code >= 400:
            logger.warning("Apify start failed actor=%s status=%d body=%s", actor_id, r.status_code, r.text[:500])
            return None
        data = r.json()
        run_data = data.get("data") or data
        return run_data.get("id")
    except Exception as exc:
        logger.warning("Apify start error actor=%s: %s", actor_id, exc)
        return None


async def _poll_actor_run(
    client: httpx.AsyncClient,
    actor_id: str,
    run_id: str,
    max_wait: int = APIFY_MAX_WAIT,
) -> dict[str, Any] | None:
    """Poll an Apify actor run until it completes. Returns run data or None."""
    url = f"{APIFY_BASE}/acts/{_actor_path(actor_id)}/runs/{run_id}"
    elapsed = 0
    while elapsed < max_wait:
        await asyncio.sleep(APIFY_POLL_INTERVAL)
        elapsed += APIFY_POLL_INTERVAL
        try:
            r = await client.get(
                url,
                params={"token": os.environ.get("APIFY_API_KEY", "").strip()},
                timeout=30.0,
            )
            if r.status_code >= 400:
                continue
            data = r.json()
            run_data = data.get("data") or data
            status = run_data.get("status", "")
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                if status != "SUCCEEDED":
                    logger.warning("Apify run %s/%s finished with status=%s", actor_id, run_id, status)
                    return None
                return run_data
        except Exception as exc:
            logger.debug("Poll error actor=%s run=%s: %s", actor_id, run_id, exc)

    logger.warning("Apify run %s/%s timed out after %ds", actor_id, run_id, max_wait)
    return None


async def _get_dataset_items(
    client: httpx.AsyncClient,
    dataset_id: str,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    """Download items from an Apify dataset."""
    url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
    try:
        r = await client.get(
            url,
            params={
                "token": os.environ.get("APIFY_API_KEY", "").strip(),
                "limit": limit,
            },
            timeout=120.0,
        )
        if r.status_code >= 400:
            logger.warning("Dataset fetch failed id=%s status=%d", dataset_id, r.status_code)
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Dataset fetch error id=%s: %s", dataset_id, exc)
        return []


async def _run_actor_and_get_results(
    client: httpx.AsyncClient,
    actor_id: str,
    run_input: dict[str, Any],
    max_wait: int = APIFY_MAX_WAIT,
) -> list[dict[str, Any]]:
    """Start actor, poll to completion, download results. Returns list of items."""
    run_id = await _start_actor_run(client, actor_id, run_input)
    if not run_id:
        return []

    run_data = await _poll_actor_run(client, actor_id, run_id, max_wait)
    if not run_data:
        return []

    dataset_id = run_data.get("defaultDatasetId")
    if not dataset_id:
        logger.warning("No dataset ID from run %s/%s", actor_id, run_id)
        return []

    return await _get_dataset_items(client, dataset_id)


# ── Actor 1: Google Maps Scraper ──────────────────────────────────────────


def _map_gmaps_result(item: dict[str, Any], vertical: str, city: str) -> dict[str, Any] | None:
    """Map a Google Maps Scraper result to a lead dict."""
    name = item.get("title") or item.get("name") or ""
    if not name:
        return None

    website = _extract_place_website(item)
    domain = _normalize_domain(website)
    if not domain:
        return None

    # Skip generic domains
    generic = {"facebook.com", "instagram.com", "twitter.com", "linkedin.com", "yelp.com", "yellowpages.com"}
    if domain in generic:
        return None

    address = item.get("address") or item.get("street") or ""
    rating = item.get("totalScore") if item.get("totalScore") is not None else item.get("rating")
    review_count = item.get("reviewsCount") if item.get("reviewsCount") is not None else item.get("reviews")
    phone = item.get("phone") or item.get("phoneUnformatted") or ""
    place_id = item.get("placeId") or item.get("cid") or ""

    # Extract city from address or use input city
    result_city = item.get("city") or city

    # Extract province
    province = item.get("state") or item.get("province") or ""
    if not province and address:
        # Try to extract 2-letter province code from address
        prov_match = re.search(r"\b([A-Z]{2})\b", address)
        if prov_match:
            province = prov_match.group(1)

    # Extract emails from result
    emails_found: list[str] = []
    # compass/crawler-google-places returns emails in various fields
    for field in ("email", "emails", "contactEmail", "emailAddress"):
        val = item.get(field)
        if isinstance(val, str) and "@" in val:
            emails_found.append(val.lower().strip())
        elif isinstance(val, list):
            for e in val:
                if isinstance(e, str) and "@" in e:
                    emails_found.append(e.lower().strip())

    return {
        "business_name": name.strip(),
        "domain": domain,
        "address": address,
        "city": result_city,
        "province": province,
        "vertical": vertical,
        "google_rating": float(rating) if rating is not None else None,
        "review_count": int(review_count) if review_count is not None else None,
        "google_place_id": str(place_id) if place_id else "",
        "phone": phone,
        "emails_from_website": emails_found,
        "status": "pending",
    }


async def _run_google_maps_single(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    vertical: str,
    city: str,
) -> list[dict[str, Any]]:
    """Run Actor 1 for a single city+vertical combination."""
    async with sem:
        queries = search_strings_for_maps(vertical, city)
        run_input = {
            "searchStringsArray": queries,
            "maxCrawledPlacesPerSearch": 80,
            "language": "en",
            "scrapeWebsiteData": True,
        }

        logger.info("Starting Google Maps scrape (%d queries): %s", len(queries), queries[:3])
        items = await _run_actor_and_get_results(client, ACTOR_GOOGLE_MAPS, run_input, max_wait=APIFY_MAX_WAIT)

        leads: list[dict[str, Any]] = []
        for item in items:
            lead = _map_gmaps_result(item, vertical, city)
            if lead:
                leads.append(lead)

        # Dedupe by domain across multiple search strings (keep richer review stats when tied)
        by_domain: dict[str, dict[str, Any]] = {}
        for lead in leads:
            d = lead.get("domain") or ""
            if not d:
                continue
            prev = by_domain.get(d)
            if prev is None:
                by_domain[d] = lead
                continue
            pr = int(prev.get("review_count") or 0)
            nr = int(lead.get("review_count") or 0)
            gr_prev = prev.get("google_rating")
            gr_new = lead.get("google_rating")
            if nr > pr or (nr == pr and (gr_new or 0) > (gr_prev or 0)):
                by_domain[d] = lead

        merged = list(by_domain.values())
        logger.info(
            "Google Maps scrape complete: %d raw rows → %d with domain → %d deduped",
            len(items),
            len(leads),
            len(merged),
        )
        return merged


async def run_actor1_google_maps(
    cities: list[str] | None = None,
    verticals: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run Actor 1 (Google Maps Scraper) for all city x vertical combinations in parallel.

    All 54 combinations (18 cities x 3 verticals) run concurrently.
    Target: under 10 minutes total.
    """
    if not os.environ.get("APIFY_API_KEY", "").strip():
        logger.error("APIFY_API_KEY not configured — skipping Google Maps scrape")
        return []

    cities = cities or CITIES
    verticals = verticals or VERTICALS

    # Concurrency is capped to APIFY_GMAPS_CONCURRENCY (default 2) so the
    # pipeline stays inside Apify's total memory budget on FREE plans. Raise
    # this via env after upgrading to a paid plan.
    sem = asyncio.Semaphore(APIFY_GMAPS_CONCURRENCY)
    all_leads: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        tasks = []
        for vertical in verticals:
            for city in cities:
                tasks.append(_run_google_maps_single(client, sem, vertical, city))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Google Maps scrape task failed: %s", result)
                continue
            all_leads.extend(result)

    # Global dedup by domain (keep highest-scored occurrence)
    domain_map: dict[str, dict[str, Any]] = {}
    for lead in all_leads:
        d = lead["domain"]
        lead["lead_score"] = score_lead(lead)
        if d not in domain_map or lead["lead_score"] > domain_map[d].get("lead_score", 0):
            domain_map[d] = lead

    deduped = list(domain_map.values())
    logger.info("Actor 1 complete: %d raw → %d unique leads from %d cities x %d verticals",
                len(all_leads), len(deduped), len(cities), len(verticals))
    return deduped



# ── Apollo contact enrichment (replaces Apify actors 2/3/4) ──────────────


async def apollo_enrich_leads(
    leads: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Enrich discovery leads with verified decision-maker contacts via Apollo.

    For every lead that doesn't already have an email from Actor 1, resolve a
    decision-maker (owner / managing partner / principal dentist / etc.) with
    a verified email, first/last name, title, phone, and LinkedIn URL via a
    single ``mixed_people/search`` call per domain. Concurrency-bounded so we
    don't flatten Apollo's rate limit.

    Returns ``{domain: contact_dict}`` where contact_dict matches the shape
    the previous actor 2/3/4 wrappers produced (``email``, ``first_name``,
    ``last_name``, ``title``, ``linkedin_url``, ``source``).
    """
    from services.apollo_enrichment import enrich_single_domain

    needs_email = [ld for ld in leads if not ld.get("_email_found")]
    if not needs_email:
        return {}

    sem = asyncio.Semaphore(max(1, APIFY_BATCH_CONCURRENCY))

    async def _enrich(lead: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        async with sem:
            try:
                hit = await enrich_single_domain(
                    domain=lead.get("domain") or "",
                    vertical=lead.get("vertical") or "dental",
                    company_name=lead.get("business_name") or lead.get("company_name") or "",
                    city=lead.get("city") or None,
                    province=lead.get("province") or None,
                )
                return (lead.get("domain") or "").strip().lower(), hit
            except Exception as exc:
                logger.warning(
                    "apollo enrich_single_domain domain=%s failed: %s",
                    lead.get("domain"), exc,
                )
                return (lead.get("domain") or "").strip().lower(), None

    results = await asyncio.gather(*[_enrich(ld) for ld in needs_email])
    out: dict[str, dict[str, Any]] = {}
    for domain, hit in results:
        if domain and hit and hit.get("email"):
            out[domain] = hit
    logger.info("Apollo enrichment: found contacts for %d/%d leads", len(out), len(needs_email))
    return out


# ── Deduplication & Suppression ───────────────────────────────────────────


async def deduplicate_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove leads already in inventory, prospects table, or suppressions."""
    if not leads or not SUPABASE_URL:
        return leads

    headers = _sb_headers()
    domains = list({lead["domain"] for lead in leads})
    existing_domains: set[str] = set()

    for table in ("aria_lead_inventory", "prospects", "suppressions"):
        for i in range(0, len(domains), 50):
            chunk = domains[i:i + 50]
            domain_filter = ",".join(chunk)
            try:
                r = httpx.get(
                    f"{SUPABASE_URL}/rest/v1/{table}",
                    headers=headers,
                    params={
                        "domain": f"in.({domain_filter})",
                        "select": "domain",
                        "limit": "500",
                    },
                    timeout=20.0,
                )
                if r.status_code < 300:
                    for row in r.json() or []:
                        d = (row.get("domain") or "").lower()
                        if d:
                            existing_domains.add(d)
            except Exception as exc:
                logger.warning("Dedup check failed for %s: %s", table, exc)

    before = len(leads)
    leads = [ld for ld in leads if ld["domain"] not in existing_domains]
    logger.info("Dedup: %d → %d leads (removed %d duplicates)", before, len(leads), before - len(leads))
    return leads



# ── Email merge (Actor 1 website email + Apollo fallback) ────────────────


def _merge_emails(
    leads: list[dict[str, Any]],
    actor1_emails: dict[str, list[str]],
    apollo_results: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge emails from Actor 1 (website-exposed) + Apollo (decision-maker).

    Priority order:
    1. Actor 1 website email (already on the public website, highest trust)
    2. Apollo decision-maker email (verified in Apollo's contact DB)

    Returns (leads_with_email, leads_without_email).
    """
    with_email: list[dict[str, Any]] = []
    without_email: list[dict[str, Any]] = []
    for lead in leads:
        domain = (lead.get("domain") or "").lower()
        email = ""
        contact_name = ""
        contact_title = ""
        phone = ""
        linkedin_url = ""
        email_finder = ""

        a1 = actor1_emails.get(domain) or []
        if a1:
            email = a1[0]
            email_finder = "google_maps_website"

        if not email:
            ap = apollo_results.get(domain)
            if ap and ap.get("email"):
                email = str(ap["email"]).lower().strip()
                contact_name = " ".join(
                    p for p in [ap.get("first_name", ""), ap.get("last_name", "")] if p
                ).strip()
                contact_title = str(ap.get("title") or "").strip()
                phone = str(ap.get("phone") or "").strip()
                linkedin_url = str(ap.get("linkedin_url") or "").strip()
                email_finder = "apollo"

        if email and "@" in email:
            lead["contact_email"] = email
            lead["contact_name"] = contact_name or lead.get("contact_name") or ""
            lead["contact_title"] = contact_title or lead.get("contact_title") or ""
            lead["contact_phone"] = phone or lead.get("contact_phone") or ""
            lead["contact_linkedin_url"] = linkedin_url or lead.get("contact_linkedin_url") or ""
            lead["email_finder"] = email_finder
            with_email.append(lead)
        elif lead.get("contact_email") and "@" in lead["contact_email"]:
            with_email.append(lead)
        else:
            lead["status"] = "suppressed"
            without_email.append(lead)

    logger.info("Email merge: %d with email, %d suppressed", len(with_email), len(without_email))
    return with_email, without_email


async def run_full_discovery(
    cities: list[str] | None = None,
    *,
    pipeline_run_id: str | None = None,
    prospect_source: str = "aria_nightly",
) -> list[dict[str, Any]]:
    """Run full discovery: Google Places / Actor 1 + Apollo contact enrichment.

    Apify actors 2/3/4 have been retired in favour of Apollo's
    ``mixed_people/search`` which is both cheaper and produces verified
    decision-maker contacts (email, name, title, phone, LinkedIn) in a single
    call. The hybrid ``apollo_people_topup`` path also tops the discovery
    queue up to the daily target when Google Places volume is low.
    """
    google_places_key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    apify_key = os.environ.get("APIFY_API_KEY", "").strip()
    if not google_places_key and not apify_key:
        logger.error(
            "Neither GOOGLE_PLACES_API_KEY nor APIFY_API_KEY configured — cannot run discovery"
        )
        return []

    # Step 1: Discovery. Google Places is preferred (cheap / rate-limit
    # friendly); Actor 1 Google Maps is only used if Places is unset.
    if google_places_key:
        from services.aria_google_places import discover_leads as _discover_google_places

        all_leads = await _discover_google_places(cities=cities)
        if not all_leads and apify_key:
            logger.warning(
                "Google Places returned 0 leads — falling back to Apify Actor 1 Google Maps"
            )
            all_leads = await run_actor1_google_maps(cities=cities)
    else:
        all_leads = await run_actor1_google_maps(cities=cities)

    # Step 2: Optional hybrid top-up via Apollo so the discovery volume hits
    # the daily target regardless of Google Places yield.
    all_leads = await _apollo_topup_if_needed(all_leads, cities=cities)

    if not all_leads:
        logger.warning("Discovery returned zero leads after Apollo top-up — stopping")
        return []

    # Capture Actor 1 / Places website emails before dedup (keyed by domain).
    actor1_emails: dict[str, list[str]] = {}
    for lead in all_leads:
        if lead.get("emails_from_website"):
            actor1_emails[lead["domain"]] = lead["emails_from_website"]

    # Step 3: Dedup against inventory + prospects + suppressions
    all_leads = await deduplicate_leads(all_leads)
    if not all_leads:
        logger.info("All leads already in inventory/CRM after dedup")
        return []

    from services.aria_prospect_pipeline import (
        bulk_upsert_discovered_prospects,
        sync_prospects_after_email_merge,
    )

    bulk_upsert_discovered_prospects(
        all_leads,
        pipeline_run_id=pipeline_run_id,
        source=prospect_source,
    )

    for lead in all_leads:
        if actor1_emails.get(lead["domain"]):
            lead["_email_found"] = True

    # Step 4: Apollo contact enrichment for every lead without a website email
    apollo_results = await apollo_enrich_leads(all_leads)

    # Step 5: Merge + sync
    with_email, without_email = _merge_emails(all_leads, actor1_emails, apollo_results)
    for ld in with_email + without_email:
        ld.pop("_email_found", None)
        ld.pop("emails_from_website", None)
    sync_prospects_after_email_merge(with_email, without_email)

    logger.info(
        "Full discovery complete: %d with email, %d suppressed",
        len(with_email), len(without_email),
    )
    return with_email + without_email


async def _apollo_topup_if_needed(
    leads: list[dict[str, Any]],
    cities: list[str] | None,
) -> list[dict[str, Any]]:
    """Top the discovery queue up with Apollo people-search when volume is low.

    The daily discovery target is configurable via
    ``crm_settings.discovery_daily_target`` (default 2000). If Google Places /
    Actor 1 returned fewer contacts than that, Apollo fills the remainder with
    verified decision-makers across the same verticals and cities.
    """
    try:
        target = _fetch_discovery_daily_target()
    except Exception:
        target = 2000
    shortfall = max(0, target - len(leads))
    if shortfall <= 0 or not APOLLO_API_KEY:
        return leads
    if not fetch_crm_bool("apollo_people_topup_enabled", default=True):
        return leads

    from services.apollo_enrichment import apollo_people_topup

    cities_list = cities or CITIES
    per_vertical = max(1, shortfall // max(1, len(VERTICALS)))
    topups: list[dict[str, Any]] = []
    for vertical in VERTICALS:
        locations = [f"{c}, USA" for c in cities_list]
        chunk = await apollo_people_topup(
            vertical=vertical, locations=locations, batch_size=per_vertical,
        )
        topups.extend(chunk)
        if len(leads) + len(topups) >= target:
            break

    if topups:
        logger.info(
            "Apollo top-up: +%d leads to reach target=%d (had %d)",
            len(topups), target, len(leads),
        )
    return leads + topups


def _fetch_discovery_daily_target() -> int:
    """Read the configured daily discovery target from crm_settings."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return 2000
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": "eq.discovery_daily_target", "select": "value", "limit": "1"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json() or []
        if rows:
            return max(100, int(str(rows[0].get("value") or "2000")))
    except Exception as exc:
        logger.warning("discovery_daily_target lookup failed: %s", exc)
    return 2000


async def run_ondemand_discovery(
    vertical: str,
    city: str,
    batch_size: int = 50,
    *,
    pipeline_run_id: str | None = None,
    prospect_source: str = "aria_chat",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run discovery for a single vertical + city with Apollo enrichment.

    Returns ``(leads, meta)`` where ``meta`` explains empty results.
    """
    vertical = canonical_vertical(vertical)
    city = normalize_city_for_discovery(city)
    apify_on = bool(os.environ.get("APIFY_API_KEY", "").strip())
    places_on = bool(os.environ.get("GOOGLE_PLACES_API_KEY", "").strip())
    meta: dict[str, Any] = {
        "vertical": vertical,
        "city": city,
        "apify_configured": apify_on,
        "apollo_configured": bool(APOLLO_API_KEY),
        "google_places_configured": places_on,
        "gmaps_raw_count": 0,
        "after_batch_trim": 0,
        "after_dedup": 0,
        "with_email": 0,
        "without_email": 0,
    }

    # Step 1: Discovery (Google Places / Actor 1 for this single combo)
    if places_on:
        from services.aria_google_places import discover_leads as _discover_google_places

        leads = await _discover_google_places(cities=[city], verticals=[vertical])
    elif apify_on:
        sem = asyncio.Semaphore(APIFY_GMAPS_CONCURRENCY)
        async with httpx.AsyncClient(timeout=120.0) as client:
            leads = await _run_google_maps_single(client, sem, vertical, city)
    else:
        leads = []

    meta["gmaps_raw_count"] = len(leads)

    if not leads and APOLLO_API_KEY and fetch_crm_bool(
        "apollo_people_topup_enabled", default=True
    ):
        from services.apollo_enrichment import apollo_people_topup

        leads = await apollo_people_topup(
            vertical=vertical,
            locations=[f"{city}, USA"],
            batch_size=batch_size,
        )
        meta["path"] = "apollo_only"
        if not leads:
            return [], meta

    if not leads:
        meta["path"] = "empty_no_discovery"
        return [], meta

    # Score + trim
    for lead in leads:
        lead["lead_score"] = lead.get("lead_score") or score_lead(lead)
    leads.sort(key=lambda x: x.get("lead_score", 0), reverse=True)
    leads = leads[:batch_size]
    meta["after_batch_trim"] = len(leads)

    # Dedup
    leads = await deduplicate_leads(leads)
    meta["after_dedup"] = len(leads)
    if not leads:
        meta["path"] = "dedup_removed_all"
        return [], meta

    from services.aria_prospect_pipeline import (
        bulk_upsert_discovered_prospects,
        sync_prospects_after_email_merge,
    )

    bulk_upsert_discovered_prospects(
        leads,
        pipeline_run_id=pipeline_run_id,
        source=prospect_source,
    )

    actor1_emails: dict[str, list[str]] = {}
    for lead in leads:
        if lead.get("emails_from_website"):
            actor1_emails[lead["domain"]] = lead["emails_from_website"]
        if actor1_emails.get(lead["domain"]) or lead.get("contact_email"):
            lead["_email_found"] = True

    apollo_results = await apollo_enrich_leads(leads)

    with_email, without_email = _merge_emails(leads, actor1_emails, apollo_results)

    for ld in with_email + without_email:
        ld.pop("_email_found", None)
        ld.pop("emails_from_website", None)

    sync_prospects_after_email_merge(with_email, without_email)

    meta["with_email"] = len(with_email)
    meta["without_email"] = len(without_email)
    meta["path"] = meta.get("path") or ("places_apollo" if places_on else "apify_apollo")
    return with_email + without_email, meta



def format_discovery_empty_message(meta: dict[str, Any]) -> str:
    """Explain zero emailable leads from on-demand discovery (for CRM / ARIA chat)."""
    v = str(meta.get("vertical") or "dental")
    c = str(meta.get("city") or "that location")
    apify = bool(meta.get("apify_configured"))
    apollo = bool(meta.get("apollo_configured"))
    path = str(meta.get("path") or "")

    if not apify and not apollo:
        return (
            "Outbound discovery cannot run: neither APIFY_API_KEY nor APOLLO_API_KEY is set on the server. "
            "Add APIFY_API_KEY for Google Maps scraping (recommended), or APOLLO_API_KEY as a fallback."
        )

    if path == "apollo_only_no_apify":
        if not apollo:
            return (
                "APIFY_API_KEY is not set and APOLLO_API_KEY is missing, so no data source could run. "
                "Configure at least one key in your deployment environment."
            )
        return (
            f"Google Maps discovery was skipped (no APIFY_API_KEY). Apollo fallback returned no people with "
            f"verified emails for {v} in {c}. Add APIFY_API_KEY for primary discovery, or try a broader location."
        )

    if path == "apollo_after_empty_gmaps":
        return (
            f"Google Maps returned no businesses with usable websites for {v} in {c}, and Apollo fallback "
            f"found no matching contacts with email. Check Apify actor runs (compass/crawler-google-places) "
            f"in the Apify console, or try another city."
        )

    if path == "dedup_removed_all":
        n = int(meta.get("after_batch_trim") or 0)
        return (
            f"Maps returned {n} candidate businesses for {v} in {c}, but all were filtered as duplicates or "
            f"already present in CRM/inventory. Increase batch size or pick a different area."
        )

    if path == "apify_full" and int(meta.get("with_email") or 0) == 0:
        n = int(meta.get("without_email") or meta.get("after_dedup") or 0)
        return (
            f"Found {n} businesses for {v} in {c} but could not resolve a contact email after LinkedIn, "
            f"Leads Finder, and website crawl. The pipeline only continues with an email; consider manual "
            f"outreach for saved prospects or raising batch size."
        )

    return (
        f"No emailable leads for {v} in {c}. "
        f"(google_maps_rows={meta.get('gmaps_raw_count', 0)}, after_dedupe={meta.get('after_dedup', 0)}.)"
    )
