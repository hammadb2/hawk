"""
ARIA Apify-based lead discovery and email enrichment.

Replaces Google Places + Prospeo + Apollo discovery with four Apify actors:
1. compass/crawler-google-places  — primary lead source (Google Maps scraper)
2. dev_fusion/mass-linkedin-profile-scraper-with-email — decision-maker finder
3. code_crafter/leads-finder — 250M+ contact database fallback
4. apify/website-email-crawler — last-resort website crawl

All 54 city x vertical combinations run in parallel for Actor 1.
Actors 2-4 run in async batches of 50 for leads still missing emails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx

from config import APOLLO_API_KEY

logger = logging.getLogger(__name__)

APIFY_API_KEY = os.environ.get("APIFY_API_KEY", "").strip()
APIFY_BASE = "https://api.apify.com/v2"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Actor IDs
ACTOR_GOOGLE_MAPS = "compass/crawler-google-places"
ACTOR_LINKEDIN = "dev_fusion/mass-linkedin-profile-scraper-with-email"
ACTOR_LEADS_FINDER = "code_crafter/leads-finder"
ACTOR_WEBSITE_CRAWLER = "apify/website-email-crawler"

# 18 Canadian cities
CITIES: list[str] = [
    "Toronto", "Vancouver", "Calgary", "Edmonton", "Ottawa", "Montreal",
    "Winnipeg", "Halifax", "Quebec City", "Saskatoon", "Regina", "Victoria",
    "Kelowna", "London Ontario", "Hamilton", "Waterloo", "Mississauga", "Brampton",
]

# Vertical search queries
VERTICAL_QUERIES: dict[str, str] = {
    "dental": "dental clinics {city} Canada",
    "legal": "law firms {city} Canada",
    "accounting": "accounting practices {city} Canada",
}

VERTICALS = list(VERTICAL_QUERIES.keys())

# Major cities for scoring bonus
MAJOR_CITIES = {"toronto", "vancouver", "calgary", "edmonton", "ottawa"}

# Decision-maker titles for LinkedIn / Leads Finder
DECISION_MAKER_TITLES = [
    "owner", "principal", "managing partner", "practice manager",
    "dentist", "lawyer", "accountant", "CPA", "director",
]

# Preferred email prefixes for website crawl (Actor 4)
PREFERRED_EMAIL_PREFIXES = ["owner", "info", "contact", "hello", "admin"]

# Polling config
APIFY_POLL_INTERVAL = 10  # seconds
APIFY_MAX_WAIT = 900  # 15 minutes max per actor run
BATCH_SIZE = 50  # parallel batch size for actors 2-4


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
    url = f"{APIFY_BASE}/acts/{actor_id}/runs?token={APIFY_API_KEY}"
    try:
        r = await client.post(url, json=run_input, timeout=60.0)
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
    url = f"{APIFY_BASE}/acts/{actor_id}/runs/{run_id}?token={APIFY_API_KEY}"
    elapsed = 0
    while elapsed < max_wait:
        await asyncio.sleep(APIFY_POLL_INTERVAL)
        elapsed += APIFY_POLL_INTERVAL
        try:
            r = await client.get(url, timeout=30.0)
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
    url = f"{APIFY_BASE}/datasets/{dataset_id}/items?token={APIFY_API_KEY}&limit={limit}"
    try:
        r = await client.get(url, timeout=120.0)
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

    website = item.get("website") or item.get("url") or ""
    domain = _normalize_domain(website)
    if not domain:
        return None

    # Skip generic domains
    generic = {"facebook.com", "instagram.com", "twitter.com", "linkedin.com", "yelp.com", "yellowpages.com"}
    if domain in generic:
        return None

    address = item.get("address") or item.get("street") or ""
    rating = item.get("totalScore") or item.get("rating")
    review_count = item.get("reviewsCount") or item.get("reviews")
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
        query = VERTICAL_QUERIES[vertical].format(city=city)
        run_input = {
            "searchStringsArray": [query],
            "maxCrawledPlacesPerSearch": 100,
            "language": "en",
            "extractEmails": True,
            "scrapeContacts": True,
        }

        logger.info("Starting Google Maps scrape: %s", query)
        items = await _run_actor_and_get_results(client, ACTOR_GOOGLE_MAPS, run_input, max_wait=APIFY_MAX_WAIT)

        leads: list[dict[str, Any]] = []
        for item in items:
            lead = _map_gmaps_result(item, vertical, city)
            if lead:
                leads.append(lead)

        logger.info("Google Maps scrape complete: %s → %d leads", query, len(leads))
        return leads


async def run_actor1_google_maps(
    cities: list[str] | None = None,
    verticals: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run Actor 1 (Google Maps Scraper) for all city x vertical combinations in parallel.

    All 54 combinations (18 cities x 3 verticals) run concurrently.
    Target: under 10 minutes total.
    """
    if not APIFY_API_KEY:
        logger.error("APIFY_API_KEY not configured — skipping Google Maps scrape")
        return []

    cities = cities or CITIES
    verticals = verticals or VERTICALS

    # All combinations run in parallel (54 tasks)
    sem = asyncio.Semaphore(60)  # generous concurrency — Apify handles rate limiting
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


# ── Actor 2: Mass LinkedIn Profile Scraper with Email ─────────────────────


async def _run_linkedin_batch(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    leads_batch: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run Actor 2 for a batch of up to 50 leads. Returns domain→contact mapping."""
    async with sem:
        # Build search queries from company name + domain
        search_queries = []
        for lead in leads_batch:
            company = lead.get("business_name", "")
            domain = lead.get("domain", "")
            search_queries.append(f"{company} {domain}")

        run_input = {
            "searchQueries": search_queries,
            "titleFilter": DECISION_MAKER_TITLES,
            "maxResults": len(leads_batch),
        }

        items = await _run_actor_and_get_results(client, ACTOR_LINKEDIN, run_input, max_wait=APIFY_MAX_WAIT)

        # Map results back to domains
        results: dict[str, dict[str, Any]] = {}
        for item in items:
            email = (item.get("email") or "").lower().strip()
            first_name = (item.get("firstName") or item.get("first_name") or "").strip()
            last_name = (item.get("lastName") or item.get("last_name") or "").strip()
            title = (item.get("title") or item.get("headline") or "").strip()
            linkedin_url = (item.get("linkedInUrl") or item.get("profileUrl") or item.get("url") or "").strip()
            company_name = (item.get("companyName") or item.get("company") or "").strip()

            # Try to match back to a lead by company name
            for lead in leads_batch:
                lead_company = (lead.get("business_name") or "").lower()
                if lead_company and company_name and lead_company in company_name.lower():
                    domain = lead["domain"]
                    if domain not in results:
                        results[domain] = {
                            "email": email,
                            "first_name": first_name,
                            "last_name": last_name,
                            "title": title,
                            "linkedin_url": linkedin_url,
                            "source": "linkedin",
                        }
                    break

        return results


async def run_actor2_linkedin(
    leads: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run Actor 2 for leads missing emails. Returns domain→contact mapping."""
    if not APIFY_API_KEY:
        return {}

    needs_email = [ld for ld in leads if not ld.get("emails_from_website")]

    if not needs_email:
        logger.info("Actor 2 skipped — all leads already have emails from websites")
        return {}

    logger.info("Actor 2: finding decision makers for %d leads via LinkedIn", len(needs_email))

    sem = asyncio.Semaphore(5)  # 5 concurrent batches of 50 = 250 simultaneous
    all_results: dict[str, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        batches = [needs_email[i:i + BATCH_SIZE] for i in range(0, len(needs_email), BATCH_SIZE)]
        tasks = [_run_linkedin_batch(client, sem, batch) for batch in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("LinkedIn batch failed: %s", result)
                continue
            all_results.update(result)

    logger.info("Actor 2 complete: found contacts for %d/%d leads", len(all_results), len(needs_email))
    return all_results


# ── Actor 3: Leads Finder (database fallback) ────────────────────────────


async def run_actor3_leads_finder(
    leads: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run Actor 3 for leads still missing emails. Returns domain→contact mapping."""
    if not APIFY_API_KEY:
        return {}

    needs_email = [ld for ld in leads if not ld.get("_email_found")]

    if not needs_email:
        logger.info("Actor 3 skipped — all leads already have emails")
        return {}

    # Group by vertical for more targeted searches
    by_vertical: dict[str, list[dict[str, Any]]] = {}
    for ld in needs_email:
        v = ld.get("vertical", "dental")
        by_vertical.setdefault(v, []).append(ld)

    logger.info("Actor 3: searching contact database for %d leads across %d verticals",
                len(needs_email), len(by_vertical))

    all_results: dict[str, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        for vertical, v_leads in by_vertical.items():
            run_input = {
                "job_title": " OR ".join(DECISION_MAKER_TITLES),
                "location": "Canada",
                "industry": vertical,
                "number_of_leads": min(len(v_leads) * 2, 1000),  # fetch extra to improve match rate
            }

            items = await _run_actor_and_get_results(client, ACTOR_LEADS_FINDER, run_input, max_wait=APIFY_MAX_WAIT)

            # Build domain index from results
            for item in items:
                email = (item.get("email") or "").lower().strip()
                if not email or "@" not in email:
                    continue
                item_domain = _normalize_domain(item.get("website") or item.get("domain") or "")
                # Also try extracting domain from email
                if not item_domain and email:
                    item_domain = email.split("@")[-1]

                if not item_domain:
                    continue

                first_name = (item.get("first_name") or item.get("firstName") or "").strip()
                last_name = (item.get("last_name") or item.get("lastName") or "").strip()
                title = (item.get("title") or item.get("job_title") or "").strip()
                linkedin_url = (item.get("linkedin_url") or item.get("linkedinUrl") or "").strip()

                # Match against our leads
                for ld in v_leads:
                    if ld["domain"] == item_domain and ld["domain"] not in all_results:
                        all_results[ld["domain"]] = {
                            "email": email,
                            "first_name": first_name,
                            "last_name": last_name,
                            "title": title,
                            "linkedin_url": linkedin_url,
                            "source": "leads_finder",
                        }
                        break

    logger.info("Actor 3 complete: found contacts for %d/%d leads", len(all_results), len(needs_email))
    return all_results


# ── Actor 4: Website Email Crawler (last resort) ─────────────────────────


async def _run_website_crawl_batch(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    leads_batch: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run Actor 4 for a batch of leads. Returns domain→contact mapping."""
    async with sem:
        start_urls = [{"url": f"https://{ld['domain']}"} for ld in leads_batch]

        run_input = {
            "startUrls": start_urls,
            "maxDepth": 2,
            "maxPagesPerCrawl": 10,
        }

        items = await _run_actor_and_get_results(client, ACTOR_WEBSITE_CRAWLER, run_input, max_wait=APIFY_MAX_WAIT)

        results: dict[str, dict[str, Any]] = {}
        for item in items:
            emails_found: list[str] = []

            # Website email crawler returns emails in various formats
            for field in ("emails", "emailAddresses", "email"):
                val = item.get(field)
                if isinstance(val, str) and "@" in val:
                    emails_found.append(val.lower().strip())
                elif isinstance(val, list):
                    for e in val:
                        if isinstance(e, str) and "@" in e:
                            emails_found.append(e.lower().strip())

            if not emails_found:
                continue

            # Determine which domain this result belongs to
            page_url = item.get("url") or item.get("pageUrl") or ""
            crawl_domain = _normalize_domain(page_url)
            if not crawl_domain:
                continue

            # Find matching lead
            matched_domain = None
            for ld in leads_batch:
                if ld["domain"] == crawl_domain or crawl_domain.endswith("." + ld["domain"]):
                    matched_domain = ld["domain"]
                    break

            if not matched_domain or matched_domain in results:
                continue

            # Pick best email: prefer those with preferred prefixes
            best_email = emails_found[0]
            for prefix in PREFERRED_EMAIL_PREFIXES:
                for em in emails_found:
                    if em.split("@")[0] == prefix:
                        best_email = em
                        break
                else:
                    continue
                break

            results[matched_domain] = {
                "email": best_email,
                "first_name": "",
                "last_name": "",
                "title": "",
                "linkedin_url": "",
                "source": "website_crawl",
            }

        return results


async def run_actor4_website_crawl(
    leads: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run Actor 4 for leads still missing emails. Returns domain→contact mapping."""
    if not APIFY_API_KEY:
        return {}

    needs_email = [ld for ld in leads if not ld.get("_email_found")]

    if not needs_email:
        logger.info("Actor 4 skipped — all leads already have emails")
        return {}

    logger.info("Actor 4: crawling %d websites for email addresses", len(needs_email))

    sem = asyncio.Semaphore(5)  # 5 concurrent batches of 50
    all_results: dict[str, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        batches = [needs_email[i:i + BATCH_SIZE] for i in range(0, len(needs_email), BATCH_SIZE)]
        tasks = [_run_website_crawl_batch(client, sem, batch) for batch in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Website crawl batch failed: %s", result)
                continue
            all_results.update(result)

    logger.info("Actor 4 complete: found emails for %d/%d leads", len(all_results), len(needs_email))
    return all_results


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


# ── Email merge and priority logic ────────────────────────────────────────


def _merge_emails(
    leads: list[dict[str, Any]],
    actor1_emails: dict[str, list[str]],
    actor2_results: dict[str, dict[str, Any]],
    actor3_results: dict[str, dict[str, Any]],
    actor4_results: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge email results from all 4 actors using priority order.

    Priority:
    1. Actor 1 website email (found on their site, highest confidence)
    2. Actor 2 LinkedIn email (verified decision maker)
    3. Actor 3 Leads Finder email (database verified)
    4. Actor 4 crawled email (scraped from website)

    Returns (leads_with_email, leads_without_email).
    """
    with_email: list[dict[str, Any]] = []
    without_email: list[dict[str, Any]] = []

    for lead in leads:
        domain = lead["domain"]
        email = ""
        contact_name = ""
        contact_title = ""
        email_finder = ""

        # Priority 1: Actor 1 website emails
        a1_emails = actor1_emails.get(domain, [])
        if a1_emails:
            email = a1_emails[0]
            email_finder = "google_maps_website"

        # Priority 2: Actor 2 LinkedIn
        if not email:
            a2 = actor2_results.get(domain)
            if a2 and a2.get("email"):
                email = a2["email"]
                contact_name = f"{a2.get('first_name', '')} {a2.get('last_name', '')}".strip()
                contact_title = a2.get("title", "")
                email_finder = "linkedin"

        # Priority 3: Actor 3 Leads Finder
        if not email:
            a3 = actor3_results.get(domain)
            if a3 and a3.get("email"):
                email = a3["email"]
                contact_name = f"{a3.get('first_name', '')} {a3.get('last_name', '')}".strip()
                contact_title = a3.get("title", "")
                email_finder = "leads_finder"

        # Priority 4: Actor 4 Website Crawl
        if not email:
            a4 = actor4_results.get(domain)
            if a4 and a4.get("email"):
                email = a4["email"]
                email_finder = "website_crawl"

        if email and "@" in email:
            lead["contact_email"] = email.lower().strip()
            lead["contact_name"] = contact_name or lead.get("contact_name") or ""
            lead["contact_title"] = contact_title or lead.get("contact_title") or ""
            lead["email_finder"] = email_finder
            with_email.append(lead)
        elif lead.get("contact_email") and "@" in lead["contact_email"]:
            # Preserve pre-existing email (e.g. from Apollo fallback)
            with_email.append(lead)
        else:
            lead["status"] = "suppressed"
            without_email.append(lead)

    logger.info("Email merge: %d with email, %d suppressed (no email)", len(with_email), len(without_email))
    return with_email, without_email


# ── Apollo last-resort fallback ───────────────────────────────────────────


async def _apollo_last_resort(
    leads: list[dict[str, Any]],
    vertical: str,
    location: str,
) -> list[dict[str, Any]]:
    """Absolute last resort: Apollo search if all 4 Apify actors returned zero results.

    This should almost never happen.
    """
    if not APOLLO_API_KEY:
        return []

    logger.warning("All 4 Apify actors returned zero — trying Apollo last resort for %s/%s", vertical, location)

    try:
        titles = {
            "dental": ["dentist", "owner", "clinic owner", "principal"],
            "legal": ["lawyer", "managing partner", "owner", "principal"],
            "accounting": ["CPA", "accountant", "owner", "principal"],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            body = {
                "page": 1,
                "per_page": 50,
                "person_titles": titles.get(vertical, titles["dental"]),
                "person_locations": [f"{location}, Canada"],
                "has_email": True,
            }
            r = await client.post(
                "https://api.apollo.io/api/v1/mixed_people/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": APOLLO_API_KEY,
                },
                json=body,
                timeout=30.0,
            )
            if r.status_code >= 400:
                return []

            data = r.json()
            people = data.get("people") or data.get("contacts") or []
            results: list[dict[str, Any]] = []
            for p in people:
                if not isinstance(p, dict):
                    continue
                email = (p.get("email") or p.get("primary_email") or "").strip()
                if not email or "@" not in email:
                    continue
                domain = _normalize_domain(p.get("organization", {}).get("website_url") or email.split("@")[-1])
                results.append({
                    "business_name": (p.get("organization", {}).get("name") or "").strip(),
                    "domain": domain,
                    "contact_email": email.lower(),
                    "contact_name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                    "contact_title": (p.get("title") or "").strip(),
                    "email_finder": "apollo_fallback",
                    "vertical": vertical,
                    "city": location,
                    "province": "",
                    "lead_score": 1,
                    "status": "pending",
                })

            logger.info("Apollo last resort: found %d leads for %s/%s", len(results), vertical, location)
            return results

    except Exception as exc:
        logger.warning("Apollo last resort failed: %s", exc)
        return []


# ── Main orchestrator ─────────────────────────────────────────────────────


async def run_full_discovery(
    cities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run the full 4-actor discovery pipeline.

    Flow:
    1. Actor 1 (Google Maps) — all city x vertical combinations in parallel
    2. Deduplicate against inventory + prospects + suppressions
    3. Actor 2 (LinkedIn) — for leads without email
    4. Actor 3 (Leads Finder) — for leads still without email
    5. Actor 4 (Website Crawler) — last resort for remaining leads
    6. Merge emails using priority order
    7. Return leads with emails (suppressed leads also returned for inventory storage)

    Args:
        cities: Optional list of cities to scrape. Defaults to CITIES constant (18 Canadian cities).

    Returns all leads with lead_score, contact_email, email_finder set.
    """
    if not APIFY_API_KEY:
        logger.error("APIFY_API_KEY not configured — cannot run discovery")
        return []

    # Step 1: Actor 1 — Google Maps
    all_leads = await run_actor1_google_maps(cities=cities)
    if not all_leads:
        logger.warning("Actor 1 returned zero leads — checking Apollo last resort")
        # Try Apollo as absolute last resort for each vertical
        for v in VERTICALS:
            for c in CITIES[:5]:  # Just top 5 cities
                fallback = await _apollo_last_resort([], v, c)
                all_leads.extend(fallback)
        if not all_leads:
            return []

    # Capture Actor 1 emails before dedup (keyed by domain)
    actor1_emails: dict[str, list[str]] = {}
    for lead in all_leads:
        if lead.get("emails_from_website"):
            actor1_emails[lead["domain"]] = lead["emails_from_website"]

    # Step 2: Deduplicate
    all_leads = await deduplicate_leads(all_leads)
    if not all_leads:
        logger.info("All leads already in inventory/CRM after dedup")
        return []

    # Mark which leads have emails from Actor 1
    for lead in all_leads:
        if actor1_emails.get(lead["domain"]):
            lead["_email_found"] = True

    # Step 3: Actor 2 — LinkedIn
    actor2_results = await run_actor2_linkedin(all_leads)
    for lead in all_leads:
        if not lead.get("_email_found") and lead["domain"] in actor2_results:
            lead["_email_found"] = True

    # Step 4: Actor 3 — Leads Finder
    actor3_results = await run_actor3_leads_finder(all_leads)
    for lead in all_leads:
        if not lead.get("_email_found") and lead["domain"] in actor3_results:
            lead["_email_found"] = True

    # Step 5: Actor 4 — Website Crawler
    actor4_results = await run_actor4_website_crawl(all_leads)

    # Step 6: Merge emails
    with_email, without_email = _merge_emails(
        all_leads, actor1_emails, actor2_results, actor3_results, actor4_results,
    )

    # Clean up internal markers
    for ld in with_email + without_email:
        ld.pop("_email_found", None)
        ld.pop("emails_from_website", None)

    # Return both — caller decides what to do with suppressed leads
    logger.info("Full discovery complete: %d with email, %d suppressed", len(with_email), len(without_email))
    return with_email + without_email


async def run_ondemand_discovery(
    vertical: str,
    city: str,
    batch_size: int = 50,
) -> list[dict[str, Any]]:
    """Run discovery for a single vertical + city (on-demand pipeline).

    Same 4-actor flow but scoped to one combination.
    """
    if not APIFY_API_KEY:
        logger.warning("APIFY_API_KEY not configured for on-demand discovery")
        # Try Apollo as absolute last resort
        return await _apollo_last_resort([], vertical, city)

    # Actor 1: single city + vertical
    sem = asyncio.Semaphore(10)
    async with httpx.AsyncClient(timeout=120.0) as client:
        leads = await _run_google_maps_single(client, sem, vertical, city)

    if not leads:
        # Apollo last resort
        return await _apollo_last_resort([], vertical, city)

    # Score and sort, take top batch_size
    for lead in leads:
        lead["lead_score"] = score_lead(lead)
    leads.sort(key=lambda x: x.get("lead_score", 0), reverse=True)
    leads = leads[:batch_size]

    # Deduplicate
    leads = await deduplicate_leads(leads)
    if not leads:
        return []

    # Capture Actor 1 emails
    actor1_emails: dict[str, list[str]] = {}
    for lead in leads:
        if lead.get("emails_from_website"):
            actor1_emails[lead["domain"]] = lead["emails_from_website"]
        if actor1_emails.get(lead["domain"]):
            lead["_email_found"] = True

    # Actor 2: LinkedIn for leads missing email
    actor2_results = await run_actor2_linkedin(leads)
    for lead in leads:
        if not lead.get("_email_found") and lead["domain"] in actor2_results:
            lead["_email_found"] = True

    # Actor 3: Leads Finder
    actor3_results = await run_actor3_leads_finder(leads)
    for lead in leads:
        if not lead.get("_email_found") and lead["domain"] in actor3_results:
            lead["_email_found"] = True

    # Actor 4: Website Crawler
    actor4_results = await run_actor4_website_crawl(leads)

    # Merge
    with_email, without_email = _merge_emails(
        leads, actor1_emails, actor2_results, actor3_results, actor4_results,
    )

    # Clean up
    for ld in with_email + without_email:
        ld.pop("_email_found", None)
        ld.pop("emails_from_website", None)

    return with_email + without_email
