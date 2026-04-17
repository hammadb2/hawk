"""
ARIA Unified Nightly Pipeline — lead inventory management.

Orchestrates: Google Places scrape → deduplicate → Prospeo/Apollo email find →
bulk ZeroBounce → domain scan (30 concurrent) → batched OpenAI email gen (20 per call) →
store as 'ready' in aria_lead_inventory.

Runs at 11pm MST via POST /api/crm/cron/nightly-pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import zoneinfo
from datetime import date, datetime, timezone
from typing import Any

import httpx

from config import (
    APOLLO_API_KEY,
    CAL_COM_BOOKING_URL,
    GOOGLE_PLACES_API_KEY,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    PROSPEO_API_KEY,
    SMARTLEAD_API_KEY,
    SUPABASE_URL,
    ZEROBOUNCE_API_KEY,
)
from services.openai_chat import chat_text_async

logger = logging.getLogger(__name__)

MST = zoneinfo.ZoneInfo("America/Edmonton")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SCANNER_URL = os.environ.get("SCANNER_URL", "https://intelligent-rejoicing-production.up.railway.app").rstrip("/")
SMARTLEAD_BASE = os.environ.get("SMARTLEAD_API_BASE", "https://server.smartlead.ai/api/v1").rstrip("/")
APOLLO_BASE = os.environ.get("APOLLO_API_BASE", "https://api.apollo.io/api/v1").rstrip("/")
PROSPEO_BASE = "https://api.prospeo.io"
ZEROBOUNCE_BULK_URL = "https://bulk.zerobounce.net/v2/sendfile"
ZEROBOUNCE_BULK_STATUS_URL = "https://bulk.zerobounce.net/v2/filestatus"
ZEROBOUNCE_BULK_RESULT_URL = "https://bulk.zerobounce.net/v2/getfile"

# Performance tuning
SCAN_CONCURRENCY = 30
SCAN_TIMEOUT = 120.0
OPENAI_BATCH_SIZE = 20
ZEROBOUNCE_POLL_INTERVAL = 15  # seconds
ZEROBOUNCE_MAX_WAIT = 600  # 10 minutes max wait for bulk verification

# CASL compliance footer
CASL_FOOTER = (
    "\n\n---\n"
    "This message was sent by Hawk Security, Calgary, AB, Canada. "
    "To unsubscribe reply STOP or click here: {{unsubscribe_link}}"
)

# Time zone → scheduled send hour mapping (8-9am local)
TIMEZONE_SCHEDULE: dict[str, dict[str, Any]] = {
    "AT": {"tz": "America/Halifax", "hour": 8},       # Atlantic
    "ET": {"tz": "America/Toronto", "hour": 8},       # Eastern
    "CT": {"tz": "America/Winnipeg", "hour": 8},      # Central
    "MT": {"tz": "America/Edmonton", "hour": 8},      # Mountain
    "PT": {"tz": "America/Vancouver", "hour": 8},     # Pacific
}

# Province → timezone mapping
PROVINCE_TZ: dict[str, str] = {
    "NL": "AT", "NS": "AT", "NB": "AT", "PE": "AT",
    "QC": "ET", "ON": "ET",
    "MB": "CT", "SK": "CT",
    "AB": "MT", "NT": "MT", "NU": "CT",
    "BC": "PT", "YT": "PT",
}


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get_setting(key: str, default: str = "") -> str:
    """Read a value from crm_settings."""
    if not SUPABASE_URL:
        return default
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
            return str(rows[0].get("value") or default)
    except Exception as exc:
        logger.warning("Failed to read setting %s: %s", key, exc)
    return default


def _set_setting(key: str, value: str) -> None:
    """Write a value to crm_settings (upsert)."""
    if not SUPABASE_URL:
        return
    try:
        chk = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}", "select": "key", "limit": "1"},
            timeout=15.0,
        )
        chk.raise_for_status()
        if chk.json():
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/crm_settings",
                headers=_sb_headers(),
                params={"key": f"eq.{key}"},
                json={"value": value},
                timeout=15.0,
            ).raise_for_status()
        else:
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/crm_settings",
                headers=_sb_headers(),
                json={"key": key, "value": value},
                timeout=15.0,
            ).raise_for_status()
    except Exception as exc:
        logger.warning("Failed to write setting %s: %s", key, exc)


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


# ── Step 1: Google Places Discovery ─────────────────────────────────────

async def step_discover_leads(cities: list[str]) -> list[dict[str, Any]]:
    """Scrape Google Places for all verticals across cities."""
    from services.aria_places_scraper import scrape_all_verticals, score_lead

    leads = await scrape_all_verticals(cities)

    # Score each lead
    for lead in leads:
        lead["lead_score"] = score_lead(lead)

    logger.info("Discovery complete: %d leads scored", len(leads))
    return leads


# ── Step 2: Deduplicate ─────────────────────────────────────────────────

async def step_deduplicate(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove leads already in inventory, prospects table, or suppressions."""
    if not leads or not SUPABASE_URL:
        return leads

    headers = _sb_headers()
    domains = list({lead["domain"] for lead in leads})
    existing_domains: set[str] = set()

    # Check aria_lead_inventory (already processed)
    for i in range(0, len(domains), 50):
        chunk = domains[i:i + 50]
        domain_filter = ",".join(chunk)
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
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
            logger.warning("Inventory dedup check failed: %s", exc)

    # Check prospects table (already contacted)
    for i in range(0, len(domains), 50):
        chunk = domains[i:i + 50]
        domain_filter = ",".join(chunk)
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/prospects",
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
            logger.warning("Prospects dedup check failed: %s", exc)

    # Check suppressions table
    for i in range(0, len(domains), 50):
        chunk = domains[i:i + 50]
        domain_filter = ",".join(chunk)
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/suppressions",
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
            logger.warning("Suppressions dedup check failed: %s", exc)

    before = len(leads)
    leads = [lead for lead in leads if lead["domain"] not in existing_domains]
    logger.info("Dedup: %d → %d leads (removed %d duplicates)", before, len(leads), before - len(leads))
    return leads


# ── Step 3: Email Finding (Prospeo primary, Apollo fallback) ────────────

async def _prospeo_find_email(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    domain: str,
) -> dict[str, Any] | None:
    """Find email via Prospeo domain search."""
    async with sem:
        try:
            r = await client.post(
                f"{PROSPEO_BASE}/api/v1/domain-search",
                headers={
                    "Content-Type": "application/json",
                    "X-KEY": PROSPEO_API_KEY,
                },
                json={"domain": domain, "limit": 1},
                timeout=30.0,
            )
            if r.status_code >= 400:
                return None
            data = r.json()
            emails = data.get("response") or data.get("emails") or []
            if isinstance(emails, list) and emails:
                em = emails[0]
                email_addr = em.get("email") or em.get("value") or ""
                if email_addr and "@" in email_addr:
                    return {
                        "email": email_addr.lower().strip(),
                        "name": em.get("first_name", ""),
                        "last_name": em.get("last_name", ""),
                        "title": em.get("title") or em.get("position") or "",
                        "source": "prospeo",
                    }
        except Exception as exc:
            logger.debug("Prospeo failed for %s: %s", domain, exc)
    return None


async def _apollo_find_email(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    domain: str,
    vertical: str,
) -> dict[str, Any] | None:
    """Fallback: find email via Apollo people search."""
    async with sem:
        try:
            titles = {
                "dental": ["dentist", "owner", "clinic owner", "principal"],
                "legal": ["lawyer", "managing partner", "owner", "principal"],
                "accounting": ["CPA", "accountant", "owner", "principal"],
            }
            body = {
                "page": 1,
                "per_page": 1,
                "person_titles": titles.get(vertical, titles["dental"]),
                "q_organization_domains": domain,
                "contact_email_status": ["verified"],
                "has_email": True,
            }
            r = await client.post(
                f"{APOLLO_BASE}/mixed_people/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": APOLLO_API_KEY,
                },
                json=body,
                timeout=30.0,
            )
            if r.status_code >= 400:
                return None
            data = r.json()
            people = data.get("people") or data.get("contacts") or []
            if people and isinstance(people[0], dict):
                p = people[0]
                email_addr = (p.get("email") or p.get("primary_email") or "").strip()
                if email_addr and "@" in email_addr:
                    return {
                        "email": email_addr.lower(),
                        "name": (p.get("first_name") or "").strip(),
                        "last_name": (p.get("last_name") or "").strip(),
                        "title": (p.get("title") or "").strip(),
                        "source": "apollo",
                    }
        except Exception as exc:
            logger.debug("Apollo fallback failed for %s: %s", domain, exc)
    return None


async def _find_email_for_lead(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    lead: dict[str, Any],
    has_prospeo: bool,
    has_apollo: bool,
) -> dict[str, Any] | None:
    """Find email for a single lead (Prospeo first, Apollo fallback). Returns enriched lead or None."""
    domain = lead["domain"]
    result = None

    if has_prospeo:
        result = await _prospeo_find_email(client, sem, domain)

    if not result and has_apollo:
        result = await _apollo_find_email(client, sem, domain, lead.get("vertical", "dental"))

    if result:
        lead["contact_email"] = result["email"]
        lead["contact_name"] = f"{result.get('name', '')} {result.get('last_name', '')}".strip() or None
        lead["contact_title"] = result.get("title") or None
        lead["email_finder"] = result["source"]
        return lead

    logger.debug("No email found for domain=%s", domain)
    return None


async def step_find_emails(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find contact emails using Prospeo (primary) with Apollo fallback.

    Runs up to 10 concurrent lookups via asyncio.gather() to meet the
    90-minute nightly pipeline target for 3,000 leads.
    """
    if not leads:
        return leads

    has_prospeo = bool(PROSPEO_API_KEY)
    has_apollo = bool(APOLLO_API_KEY)
    if not has_prospeo and not has_apollo:
        logger.warning("No email finder API keys configured — skipping email finding")
        return leads

    sem = asyncio.Semaphore(10)  # 10 concurrent email lookups

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [
            _find_email_for_lead(client, sem, lead, has_prospeo, has_apollo)
            for lead in leads
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Email finding task failed: %s", r)
        elif r is not None:
            enriched.append(r)

    logger.info("Email finding: %d/%d leads got emails", len(enriched), len(leads))
    return enriched


# ── Step 4: Bulk ZeroBounce Verification ────────────────────────────────

async def step_bulk_verify_emails(leads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Verify emails using ZeroBounce bulk API.

    Returns (verified_leads, suppressed_leads) so suppressed leads can be
    stored in inventory with status='suppressed' to prevent re-processing.
    """
    if not leads or not ZEROBOUNCE_API_KEY:
        logger.warning("ZeroBounce not configured — skipping verification, keeping all leads")
        for lead in leads:
            lead["zero_bounce_result"] = "valid"
        return leads, []

    # Build CSV content for bulk upload
    csv_lines = ["email"]
    email_to_lead: dict[str, dict[str, Any]] = {}
    for lead in leads:
        email = lead.get("contact_email", "")
        if email:
            csv_lines.append(email)
            email_to_lead[email.lower()] = lead

    if len(csv_lines) <= 1:
        return leads, []

    csv_content = "\n".join(csv_lines)

    try:
        # Submit bulk file
        async with httpx.AsyncClient(timeout=60.0) as client:
            # ZeroBounce bulk API expects multipart form
            r = await client.post(
                ZEROBOUNCE_BULK_URL,
                data={
                    "api_key": ZEROBOUNCE_API_KEY,
                    "email_address_column": "1",
                    "has_header_row": "true",
                    "return_url": "",
                },
                files={"file": ("emails.csv", csv_content.encode(), "text/csv")},
                timeout=60.0,
            )
            if r.status_code >= 400:
                logger.error("ZeroBounce bulk upload failed: %s", r.text[:500])
                # Fallback: keep all leads as valid
                for lead in leads:
                    lead["zero_bounce_result"] = "valid"
                return leads, []

            upload_data = r.json()
            file_id = upload_data.get("file_id")
            if not file_id:
                logger.error("ZeroBounce bulk upload returned no file_id: %s", upload_data)
                for lead in leads:
                    lead["zero_bounce_result"] = "valid"
                return leads, []

            logger.info("ZeroBounce bulk submitted file_id=%s (%d emails)", file_id, len(csv_lines) - 1)

            # Poll for completion
            elapsed = 0
            while elapsed < ZEROBOUNCE_MAX_WAIT:
                await asyncio.sleep(ZEROBOUNCE_POLL_INTERVAL)
                elapsed += ZEROBOUNCE_POLL_INTERVAL

                status_r = await client.get(
                    ZEROBOUNCE_BULK_STATUS_URL,
                    params={"api_key": ZEROBOUNCE_API_KEY, "file_id": file_id},
                    timeout=30.0,
                )
                if status_r.status_code >= 400:
                    continue

                status_data = status_r.json()
                file_status = (status_data.get("file_status") or "").lower()
                complete_pct = status_data.get("complete_percentage")

                if file_status == "complete" or complete_pct == "100%":
                    break

                logger.debug("ZeroBounce bulk status: %s (%s)", file_status, complete_pct)

            # Download results
            result_r = await client.get(
                ZEROBOUNCE_BULK_RESULT_URL,
                params={"api_key": ZEROBOUNCE_API_KEY, "file_id": file_id},
                timeout=60.0,
            )
            if result_r.status_code >= 400:
                logger.error("ZeroBounce bulk results download failed: %s", result_r.text[:500])
                for lead in leads:
                    lead["zero_bounce_result"] = "valid"
                return leads, []

            # Parse CSV results
            result_lines = result_r.text.strip().split("\n")
            if len(result_lines) < 2:
                for lead in leads:
                    lead["zero_bounce_result"] = "valid"
                return leads, []

            # Find email and status column indices from header
            header = result_lines[0].lower().split(",")
            email_col = 0
            status_col = -1
            for idx, col in enumerate(header):
                if "email" in col and "address" in col:
                    email_col = idx
                elif col.strip() == "email":
                    email_col = idx
                elif col.strip() == "zerobounce status" or col.strip() == "zb_status" or col.strip() == "status":
                    status_col = idx

            if status_col == -1:
                # Try to find status column by name
                for idx, col in enumerate(header):
                    if "status" in col:
                        status_col = idx
                        break

            # Map results
            zb_map: dict[str, str] = {}
            for line in result_lines[1:]:
                parts = line.split(",")
                if len(parts) > max(email_col, status_col):
                    email = parts[email_col].strip().strip('"').lower()
                    status = parts[status_col].strip().strip('"').lower() if status_col >= 0 else "valid"
                    zb_map[email] = status

            verified: list[dict[str, Any]] = []
            suppressed: list[dict[str, Any]] = []
            for lead in leads:
                email = (lead.get("contact_email") or "").lower()
                zb_status = zb_map.get(email, "valid")

                if zb_status in ("valid",):
                    lead["zero_bounce_result"] = "valid"
                    verified.append(lead)
                elif zb_status in ("catch-all", "catch_all"):
                    lead["zero_bounce_result"] = "catch_all"
                    verified.append(lead)
                elif zb_status in ("invalid", "disposable", "spamtrap", "abuse", "do_not_mail"):
                    lead["zero_bounce_result"] = "invalid"
                    lead["status"] = "suppressed"
                    lead["suppression_reason"] = f"zerobounce_{zb_status}"
                    suppressed.append(lead)
                else:
                    lead["zero_bounce_result"] = "removed"
                    lead["status"] = "suppressed"
                    lead["suppression_reason"] = f"zerobounce_{zb_status}"
                    suppressed.append(lead)

            logger.info("ZeroBounce bulk: %d verified, %d suppressed", len(verified), len(suppressed))
            return verified, suppressed

    except Exception as exc:
        logger.exception("ZeroBounce bulk verification failed: %s", exc)
        # Fallback: keep all leads
        for lead in leads:
            lead["zero_bounce_result"] = "valid"
        return leads, []


# ── Step 5: Domain Scanning (30 concurrent) ─────────────────────────────

async def _scan_domain(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    domain: str,
) -> dict[str, Any]:
    """Run Hawk scanner on a single domain."""
    async with sem:
        try:
            r = await client.post(
                f"{SCANNER_URL}/v1/scan/sync",
                json={"domain": domain, "scan_depth": "fast"},
                timeout=SCAN_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("score") is not None:
                return data
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.debug("Scan failed domain=%s: %s", domain, exc)
            return {"error": str(exc)[:300]}


async def step_scan_domains(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scan all lead domains concurrently (30 at a time)."""
    if not leads:
        return leads

    sem = asyncio.Semaphore(SCAN_CONCURRENCY)
    results: dict[str, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=SCAN_TIMEOUT + 10) as client:
        tasks = {}
        for lead in leads:
            domain = lead["domain"]
            if domain not in tasks:
                tasks[domain] = _scan_domain(client, sem, domain)

        domain_results = await asyncio.gather(*[tasks[d] for d in tasks], return_exceptions=True)
        for domain, result in zip(tasks.keys(), domain_results):
            if isinstance(result, Exception):
                results[domain] = {"error": str(result)[:300]}
            else:
                results[domain] = result

    # Enrich leads with scan data
    for lead in leads:
        scan = results.get(lead["domain"], {})
        score = scan.get("score")
        findings = scan.get("findings") or []

        lead["hawk_score"] = int(score) if score is not None else None
        lead["scan_data"] = scan

        # Extract top vulnerability
        if findings:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            findings_sorted = sorted(
                [f for f in findings if isinstance(f, dict)],
                key=lambda f: severity_order.get((f.get("severity") or "info").lower(), 99),
            )
            if findings_sorted:
                top = findings_sorted[0]
                title = top.get("title") or top.get("name") or ""
                interp = top.get("interpretation") or top.get("plain_english") or top.get("description") or ""
                sev = (top.get("severity") or "").upper()
                lead["vulnerability_found"] = f"[{sev}] {title}"
                if interp:
                    lead["vulnerability_found"] += f" — {interp[:200]}"
            else:
                lead["no_finding"] = True
        else:
            lead["no_finding"] = True

        lead["status"] = "scanned"

    logger.info("Scanning complete: %d domains scanned", len(leads))
    return leads


# ── Step 6: Batched OpenAI Email Generation (20 per call) ───────────────

EMAIL_SYSTEM_PROMPT = """You are ARIA, the outbound email writer for Hawk Security — a Canadian cybersecurity company.

You write short, high-converting cold emails for Canadian small businesses (dental clinics, law firms, accounting practices).

Rules:
1. Open with the most alarming finding. Never open with "I hope this finds you well" or "My name is"
2. Use their actual domain name in the first sentence
3. Explain the finding in plain English for their specific business type
4. End with one low-friction ask: offer to send the full report or book a 15-min call
5. Under 100 words for the body
6. Subject line must mention their domain or a specific finding
7. Subject line must be lowercase
8. Never use: leverage, synergy, touch base, circle back, reach out, game-changer
9. Sound like a real person who actually ran a scan
10. No hyphens or dashes anywhere in the output
11. No bullet points or numbered lists in the body
12. Short punchy sentences. No sentence over 20 words.
13. If no vulnerability was found, use a PIPEDA compliance angle instead
14. Vary your opening line every time

Return ONLY valid JSON array with objects: [{"email": "lead_email", "subject": "...", "body": "..."}]
"""


async def _generate_batch(
    leads_batch: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Generate emails for a batch of up to 20 leads in one OpenAI call."""
    booking_url = CAL_COM_BOOKING_URL or "https://cal.com/hawksecurity/15min"

    prompts = []
    for lead in leads_batch:
        first_name = (lead.get("contact_name") or "").split()[0] if lead.get("contact_name") else "there"
        domain = lead.get("domain", "")
        company = lead.get("business_name", "")
        vulnerability = lead.get("vulnerability_found", "")
        vertical = lead.get("vertical", "business")

        if vulnerability:
            prompts.append(
                f"- Email: {lead.get('contact_email')}, Name: {first_name}, Company: {company}, "
                f"Domain: {domain}, Vertical: {vertical}, "
                f"Vulnerability: {vulnerability}, Booking: {booking_url}"
            )
        else:
            prompts.append(
                f"- Email: {lead.get('contact_email')}, Name: {first_name}, Company: {company}, "
                f"Domain: {domain}, Vertical: {vertical}, "
                f"No vulnerability found. Use PIPEDA compliance angle. Booking: {booking_url}"
            )

    user_msg = f"Generate personalized cold emails for these {len(leads_batch)} leads:\n" + "\n".join(prompts)

    try:
        raw = await chat_text_async(
            api_key=OPENAI_API_KEY,
            user_messages=[{"role": "user", "content": user_msg}],
            max_tokens=4000,
            system=EMAIL_SYSTEM_PROMPT,
            model=OPENAI_MODEL,
        )

        # Parse JSON array
        text = raw.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m:
                text = m.group(1).strip()

        start = text.index("[")
        end = text.rindex("]") + 1
        emails_list = json.loads(text[start:end])

        result: dict[str, dict[str, str]] = {}
        for item in emails_list:
            if isinstance(item, dict):
                email_key = (item.get("email") or "").lower()
                subject = (item.get("subject") or "").strip()
                body = (item.get("body") or "").strip()
                if email_key and subject and body:
                    # Sanitize: remove hyphens
                    subject = re.sub(r"\s*[-—–]\s*", ", ", subject).strip()
                    body = re.sub(r"\s*[-—–]\s*", ", ", body).strip()
                    result[email_key] = {"subject": subject.lower(), "body": body}

        return result
    except Exception as exc:
        logger.warning("OpenAI batch email generation failed: %s", exc)
        return {}


async def step_generate_emails(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate personalized emails in batches of 20."""
    if not leads or not OPENAI_API_KEY:
        logger.warning("OpenAI not configured — skipping email generation")
        return leads

    booking_url = CAL_COM_BOOKING_URL or "https://cal.com/hawksecurity/15min"
    generated = 0

    for i in range(0, len(leads), OPENAI_BATCH_SIZE):
        batch = leads[i:i + OPENAI_BATCH_SIZE]
        results = await _generate_batch(batch)

        for lead in batch:
            email_key = (lead.get("contact_email") or "").lower()
            email_content = results.get(email_key)

            if email_content:
                # Append CASL footer to body
                body_with_footer = email_content["body"] + CASL_FOOTER
                lead["email_subject"] = email_content["subject"]
                lead["email_body"] = body_with_footer
                lead["status"] = "personalized"
                generated += 1
            else:
                # Fallback: generate a template
                first_name = (lead.get("contact_name") or "").split()[0] if lead.get("contact_name") else "there"
                domain = lead.get("domain", "")
                vuln = lead.get("vulnerability_found", "")
                vertical = lead.get("vertical", "business")

                if vuln:
                    lead["email_subject"] = f"found an issue on {domain}"
                    lead["email_body"] = (
                        f"{first_name},\n\n"
                        f"We ran a security scan on {domain} and found: {vuln[:150]}.\n\n"
                        f"An attacker could exploit this to access your systems or data.\n\n"
                        f"I can walk you through what we found in 15 minutes.\n\n"
                        f"{booking_url}"
                    ) + CASL_FOOTER
                else:
                    lead["email_subject"] = f"quick security question about {domain}"
                    lead["email_body"] = (
                        f"{first_name},\n\n"
                        f"Under PIPEDA, Canadian {vertical} practices must protect client data. "
                        f"We ran a check on {domain} and wanted to share what we found.\n\n"
                        f"Would you have 15 minutes this week?\n\n"
                        f"{booking_url}"
                    ) + CASL_FOOTER

                lead["status"] = "personalized"
                generated += 1

    logger.info("Email generation: %d/%d leads personalized", generated, len(leads))
    return leads


# ── Step 7: Calculate scheduled send time ───────────────────────────────

def _compute_send_time(province: str) -> datetime | None:
    """Compute next 8am local time for the lead's province."""
    tz_code = PROVINCE_TZ.get(province, "ET")
    tz_info = TIMEZONE_SCHEDULE.get(tz_code, TIMEZONE_SCHEDULE["ET"])
    local_tz = zoneinfo.ZoneInfo(tz_info["tz"])
    hour = tz_info["hour"]

    # Tomorrow at 8am local time
    now = datetime.now(local_tz)
    tomorrow = now.date()
    if now.hour >= hour:
        from datetime import timedelta
        tomorrow = now.date() + timedelta(days=1)

    send_local = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, 0, 0, tzinfo=local_tz)
    return send_local.astimezone(timezone.utc)


def step_schedule_sends(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add time-zone-aware scheduled send times to each lead."""
    for lead in leads:
        province = lead.get("province") or ""
        send_time = _compute_send_time(province)
        if send_time:
            lead["scheduled_send_at"] = send_time.isoformat()
        lead["status"] = "ready"
    return leads


# ── Step 8: Store in inventory ──────────────────────────────────────────

def step_store_inventory(leads: list[dict[str, Any]], run_date: date) -> int:
    """Batch insert leads into aria_lead_inventory."""
    if not leads or not SUPABASE_URL:
        return 0

    headers = _sb_headers()
    stored = 0

    # Batch insert in chunks of 100
    for i in range(0, len(leads), 100):
        batch = leads[i:i + 100]
        rows = []
        for lead in batch:
            rows.append({
                "business_name": lead.get("business_name", ""),
                "domain": lead["domain"],
                "address": lead.get("address"),
                "city": lead.get("city"),
                "province": lead.get("province"),
                "vertical": lead.get("vertical", ""),
                "google_rating": lead.get("google_rating"),
                "review_count": lead.get("review_count"),
                "google_place_id": lead.get("google_place_id"),
                "contact_name": lead.get("contact_name"),
                "contact_email": lead.get("contact_email"),
                "contact_title": lead.get("contact_title"),
                "email_finder": lead.get("email_finder"),
                "zero_bounce_result": lead.get("zero_bounce_result"),
                "zero_bounce_data": lead.get("zero_bounce_data", {}),
                "hawk_score": lead.get("hawk_score"),
                "vulnerability_found": lead.get("vulnerability_found"),
                "no_finding": lead.get("no_finding", False),
                "scan_data": lead.get("scan_data", {}),
                "email_subject": lead.get("email_subject"),
                "email_body": lead.get("email_body"),
                "lead_score": lead.get("lead_score", 0),
                "status": lead.get("status", "ready"),
                "scheduled_send_at": lead.get("scheduled_send_at"),
                "nightly_run_date": str(run_date),
            })

        try:
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
                headers={**headers, "Prefer": "return=minimal,resolution=merge-duplicates"},
                json=rows,
                timeout=60.0,
            )
            if r.status_code < 300:
                stored += len(batch)
            else:
                logger.error("Inventory batch insert failed: %s", r.text[:500])
                # Try one-by-one for failed batch
                for row in rows:
                    try:
                        r2 = httpx.post(
                            f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
                            headers=headers,
                            json=row,
                            timeout=15.0,
                        )
                        if r2.status_code < 300:
                            stored += 1
                    except Exception:
                        pass
        except Exception as exc:
            logger.exception("Inventory batch insert error: %s", exc)

    logger.info("Inventory stored: %d/%d leads", stored, len(leads))
    return stored


# ── Full Nightly Pipeline Orchestrator ──────────────────────────────────

async def run_nightly_pipeline() -> dict[str, Any]:
    """
    Execute the full nightly pipeline:
    Google Places → Deduplicate → Email Find → Bulk ZeroBounce →
    Domain Scan → Batched OpenAI → Schedule → Store as 'ready'.

    Returns summary stats.
    """
    start_time = datetime.now(timezone.utc)
    run_date = datetime.now(MST).date()
    stats: dict[str, Any] = {
        "ok": True,
        "run_date": str(run_date),
        "leads_discovered": 0,
        "leads_after_dedup": 0,
        "leads_with_email": 0,
        "leads_verified": 0,
        "leads_scanned": 0,
        "leads_personalized": 0,
        "leads_stored": 0,
        "duration_seconds": 0,
    }

    # Check if nightly pipeline is enabled
    enabled = _get_setting("pipeline_nightly_enabled", "true")
    if enabled.lower() not in ("true", "1", "yes"):
        return {**stats, "ok": False, "skipped": True, "reason": "pipeline_nightly_enabled is false"}

    # Get cities list
    cities_json = _get_setting(
        "google_places_cities",
        '["Toronto","Vancouver","Calgary","Edmonton","Ottawa","Montreal","Winnipeg","Halifax","Quebec City","Saskatoon","Regina","Victoria","Kelowna","London","Hamilton","Waterloo","Mississauga","Brampton"]',
    )
    try:
        cities = json.loads(cities_json)
    except (json.JSONDecodeError, TypeError):
        cities = ["Toronto", "Vancouver", "Calgary", "Edmonton", "Ottawa"]

    try:
        # Step 1: Discover leads from Google Places
        leads = await step_discover_leads(cities)
        stats["leads_discovered"] = len(leads)
        if not leads:
            stats["ok"] = False
            stats["error"] = "No leads discovered from Google Places"
            return stats

        # Step 2: Deduplicate against inventory + CRM + suppressions
        leads = await step_deduplicate(leads)
        stats["leads_after_dedup"] = len(leads)
        if not leads:
            return {**stats, "ok": True, "message": "All leads already in inventory or CRM"}

        # Step 3: Find emails (Prospeo → Apollo)
        leads = await step_find_emails(leads)
        stats["leads_with_email"] = len(leads)
        if not leads:
            return {**stats, "ok": True, "message": "No emails found for discovered leads"}

        # Step 4: Bulk ZeroBounce verification
        leads, suppressed_leads = await step_bulk_verify_emails(leads)
        stats["leads_verified"] = len(leads)
        stats["leads_suppressed"] = len(suppressed_leads)

        # Store suppressed leads immediately so dedup catches them next run
        if suppressed_leads:
            suppressed_stored = step_store_inventory(suppressed_leads, run_date)
            logger.info("Stored %d suppressed leads in inventory for dedup", suppressed_stored)

        if not leads:
            return {**stats, "ok": True, "message": "All leads failed email verification"}

        # Step 5: Domain scanning (30 concurrent)
        leads = await step_scan_domains(leads)
        stats["leads_scanned"] = len(leads)

        # Step 6: Batched OpenAI email generation (20 per call)
        leads = await step_generate_emails(leads)
        stats["leads_personalized"] = len([l for l in leads if l.get("email_subject")])

        # Step 7: Schedule send times by province timezone
        leads = step_schedule_sends(leads)

        # Step 8: Store in inventory
        stored = step_store_inventory(leads, run_date)
        stats["leads_stored"] = stored

    except Exception as exc:
        logger.exception("Nightly pipeline failed: %s", exc)
        stats["ok"] = False
        stats["error"] = str(exc)[:1000]

    stats["duration_seconds"] = int((datetime.now(timezone.utc) - start_time).total_seconds())
    logger.info("Nightly pipeline complete: %s", json.dumps(stats))

    # Send CEO SMS summary
    _send_nightly_summary_sms(stats)

    return stats


def _send_nightly_summary_sms(stats: dict[str, Any]) -> None:
    """Send CEO SMS summary of nightly pipeline run."""
    try:
        from services.crm_openphone import send_ceo_sms

        msg = (
            "ARIA nightly pipeline complete.\n"
            f"Date: {stats.get('run_date', '—')}\n"
            f"Discovered: {stats.get('leads_discovered', 0)}\n"
            f"After dedup: {stats.get('leads_after_dedup', 0)}\n"
            f"Emails found: {stats.get('leads_with_email', 0)}\n"
            f"Verified: {stats.get('leads_verified', 0)}\n"
            f"Personalized: {stats.get('leads_personalized', 0)}\n"
            f"Ready for dispatch: {stats.get('leads_stored', 0)}\n"
            f"Duration: {stats.get('duration_seconds', 0)}s"
        )
        send_ceo_sms(msg)
    except Exception:
        logger.exception("Nightly summary SMS failed")


# ── Inventory Query Helpers (used by morning dispatch + chat) ───────────

def get_ready_leads(
    vertical: str | None = None,
    city: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Fetch leads with status='ready' from inventory, ordered by score."""
    if not SUPABASE_URL:
        return []

    params: dict[str, str] = {
        "status": "eq.ready",
        "select": "*",
        "order": "lead_score.desc,created_at.asc",
        "limit": str(limit),
    }
    if vertical:
        params["vertical"] = f"eq.{vertical}"
    if city:
        params["city"] = f"ilike.%{city}%"

    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
            headers=_sb_headers(),
            params=params,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        logger.exception("Failed to fetch ready leads: %s", exc)
        return []


def mark_leads_dispatched(lead_ids: list[str], campaign_id: str) -> int:
    """Mark leads as dispatched after loading into Smartlead."""
    if not lead_ids or not SUPABASE_URL:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    updated = 0

    for i in range(0, len(lead_ids), 50):
        chunk = lead_ids[i:i + 50]
        id_filter = ",".join(chunk)
        try:
            r = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
                headers=_sb_headers(),
                params={"id": f"in.({id_filter})"},
                json={
                    "status": "dispatched",
                    "smartlead_campaign_id": campaign_id,
                    "dispatched_at": now,
                    "updated_at": now,
                },
                timeout=30.0,
            )
            if r.status_code < 300:
                updated += len(chunk)
        except Exception as exc:
            logger.warning("Failed to mark leads dispatched: %s", exc)

    return updated
