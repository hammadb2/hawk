"""
ARIA Outbound Pipeline — full autonomous lead-to-email pipeline.

Apify 4-actor discovery (Google Maps + LinkedIn + Leads Finder + Website Crawler)
→ ZeroBounce → Hawk Domain Scan → OpenAI Email Gen → Smartlead.

First checks aria_lead_inventory for pre-built leads (instant dispatch).
Falls back to on-demand Apify discovery if inventory is empty.
Apollo kept as absolute last resort only.

Each step updates aria_pipeline_runs and aria_pipeline_leads in real time so
the frontend can display a live progress tracker.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from config import (
    CAL_COM_BOOKING_URL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    SMARTLEAD_API_KEY,
    SUPABASE_URL,
)
from services.openai_chat import chat_text_async

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
APOLLO_BASE = os.environ.get("APOLLO_API_BASE", "https://api.apollo.io/api/v1").rstrip("/")
CLAY_API_KEY = os.environ.get("CLAY_API_KEY", "").strip()
CLAY_BASE = os.environ.get("CLAY_API_BASE", "https://api.clay.com/v1").rstrip("/")
ZEROBOUNCE_API_KEY = os.environ.get("ZEROBOUNCE_API_KEY", "").strip()
ZEROBOUNCE_VALIDATE = "https://api.zerobounce.net/v2/validate"
SMARTLEAD_BASE = os.environ.get("SMARTLEAD_API_BASE", "https://server.smartlead.ai/api/v1").rstrip("/")
SCANNER_URL = os.environ.get("SCANNER_URL", "https://intelligent-rejoicing-production.up.railway.app").rstrip("/")

DRY_RUN = os.environ.get("ARIA_PIPELINE_DRY_RUN", "").strip() == "1"

SCAN_TIMEOUT = 120.0
SCAN_CONCURRENCY = 10

# Vertical → Apollo search config
VERTICAL_CONFIG: dict[str, dict[str, Any]] = {
    "dental": {
        "keywords": ["dental", "dentistry", "dental clinic"],
        "titles": ["dentist", "dental office manager", "clinic owner", "owner", "principal", "managing partner", "practice manager"],
    },
    "legal": {
        "keywords": ["law firm", "legal services", "lawyer"],
        "titles": ["lawyer", "solicitor", "managing partner", "law firm owner", "owner", "principal", "practice manager"],
    },
    "accounting": {
        "keywords": ["accounting", "CPA", "bookkeeping"],
        "titles": ["CPA", "accountant", "accounting firm owner", "owner", "principal", "managing partner", "practice manager"],
    },
}


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


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


# ── Pipeline Run DB helpers ───────────────────────────────────────────────

def _update_run(run_id: str, patch: dict[str, Any]) -> None:
    """Patch aria_pipeline_runs row."""
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
            headers=_sb_headers(),
            params={"id": f"eq.{run_id}"},
            json=patch,
            timeout=20.0,
        ).raise_for_status()
    except Exception as exc:
        logger.exception("Failed to update pipeline run %s: %s", run_id, exc)


def _insert_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Insert batch of leads into aria_pipeline_leads. Returns inserted rows."""
    if not leads:
        return []
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_pipeline_leads",
            headers=_sb_headers(),
            json=leads,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json() if r.status_code < 300 else []
    except Exception as exc:
        logger.exception("Failed to insert pipeline leads: %s", exc)
        return []


def _update_lead(lead_id: str, patch: dict[str, Any]) -> None:
    """Patch a single aria_pipeline_leads row."""
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/aria_pipeline_leads",
            headers=_sb_headers(),
            params={"id": f"eq.{lead_id}"},
            json=patch,
            timeout=20.0,
        ).raise_for_status()
    except Exception as exc:
        logger.exception("Failed to update pipeline lead %s: %s", lead_id, exc)


def _get_run(run_id: str) -> dict[str, Any] | None:
    """Fetch a pipeline run row."""
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
            headers=_sb_headers(),
            params={"id": f"eq.{run_id}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.exception("Failed to fetch pipeline run %s: %s", run_id, exc)
        return None


def _get_run_leads(run_id: str, status_filter: str | None = None) -> list[dict[str, Any]]:
    """Fetch leads for a pipeline run, optionally filtered by status."""
    params: dict[str, str] = {
        "run_id": f"eq.{run_id}",
        "select": "*",
        "order": "created_at.asc",
        "limit": "500",
    }
    if status_filter:
        params["status"] = f"eq.{status_filter}"
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_pipeline_leads",
            headers=_sb_headers(),
            params=params,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        logger.exception("Failed to fetch pipeline leads for run %s: %s", run_id, exc)
        return []


def _is_run_paused(run_id: str) -> bool:
    """Check if a run has been paused."""
    run = _get_run(run_id)
    return run is not None and run.get("status") == "paused"


# ── Step 1: Apollo Pull ──────────────────────────────────────────────────

def _apollo_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY,
    }


def step_apollo_pull(
    run_id: str,
    vertical: str,
    location: str,
    batch_size: int,
) -> list[dict[str, Any]]:
    """Pull leads from Apollo by vertical and location. Returns mapped leads."""
    _update_run(run_id, {"current_step": "apify_discover"})

    if DRY_RUN or not APOLLO_API_KEY:
        logger.info("ARIA pipeline: Apollo dry run / no API key — generating stub leads")
        stubs = []
        for i in range(min(batch_size, 5)):
            stubs.append({
                "run_id": run_id,
                "company_name": f"Test {vertical.title()} Co {i+1}",
                "domain": f"test{vertical}{i+1}.ca",
                "contact_name": f"John Doe {i+1}",
                "contact_email": f"john{i+1}@test{vertical}{i+1}.ca",
                "vertical": vertical,
                "apollo_data": {"stub": True, "location": location},
                "status": "pulled",
            })
        inserted = _insert_leads(stubs)
        _update_run(run_id, {"leads_pulled": len(inserted)})
        return inserted

    config = VERTICAL_CONFIG.get(vertical, VERTICAL_CONFIG["dental"])
    body: dict[str, Any] = {
        "page": 1,
        "per_page": min(batch_size, 100),
        "person_titles": config["titles"],
        "person_locations": [location],
        "organization_num_employees_ranges": ["1,50"],
        "contact_email_status": ["verified", "unverified"],
        "q_organization_keyword_tags": config["keywords"][:5],
    }

    # ``mixed_people/api_search`` does not return email addresses — they come
    # back locked (empty or ``email_not_unlocked@…``). Collect the raw person
    # rows first, unlock emails in a follow-up ``people/bulk_match`` call, then
    # filter + shape into lead records.
    raw_people: list[dict[str, Any]] = []
    pages_needed = (batch_size + 99) // 100

    with httpx.Client(timeout=120.0) as client:
        for page in range(1, pages_needed + 1):
            if _is_run_paused(run_id):
                break
            body["page"] = page
            try:
                r = client.post(
                    f"{APOLLO_BASE}/mixed_people/api_search",
                    headers=_apollo_headers(),
                    json=body,
                    timeout=120.0,
                )
                r.raise_for_status()
                data = r.json()
                people = data.get("people") or data.get("contacts") or []
                for p in people:
                    if not isinstance(p, dict):
                        continue
                    if not p.get("id"):
                        continue
                    raw_people.append(p)
                if len(raw_people) >= batch_size:
                    break
            except Exception as exc:
                logger.exception("Apollo search page %d failed: %s", page, exc)
                break

        # Unlock emails in chunks of 10 via people/bulk_match.
        unlocked_by_id: dict[str, str] = {}
        for i in range(0, len(raw_people), 10):
            chunk = raw_people[i : i + 10]
            ids = [str(p["id"]) for p in chunk]
            try:
                m = client.post(
                    f"{APOLLO_BASE}/people/bulk_match",
                    headers=_apollo_headers(),
                    json={
                        "reveal_personal_emails": True,
                        "details": [{"id": pid} for pid in ids],
                    },
                    timeout=120.0,
                )
                if m.status_code >= 400:
                    logger.warning(
                        "Apollo bulk_match HTTP %s body=%s",
                        m.status_code, m.text[:300],
                    )
                    continue
                matches = (m.json() or {}).get("matches") or (m.json() or {}).get("people") or []
                for match in matches:
                    if not isinstance(match, dict) or not match.get("id"):
                        continue
                    em = (match.get("email") or match.get("primary_email") or "").strip()
                    if em and "email_not_unlocked" not in em:
                        unlocked_by_id[str(match["id"])] = em.lower()
            except Exception as exc:
                logger.warning("Apollo bulk_match chunk failed: %s", exc)
                continue

    all_people: list[dict[str, Any]] = []
    for p in raw_people:
        pid = str(p.get("id") or "")
        email = unlocked_by_id.get(pid) or (p.get("email") or "").strip().lower()
        if not email or "email_not_unlocked" in email:
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
        domain = _normalize_domain(str(website))
        if not domain:
            continue
        first_name = (p.get("first_name") or "").strip()
        last_name = (p.get("last_name") or "").strip()
        company = (org.get("name") or "").strip()

        all_people.append({
            "run_id": run_id,
            "company_name": company,
            "domain": domain,
            "contact_name": f"{first_name} {last_name}".strip(),
            "contact_email": email,
            "vertical": vertical,
            "apollo_data": {
                "person_id": p.get("id"),
                "first_name": first_name,
                "last_name": last_name,
                "title": (p.get("title") or "").strip(),
                "city": (p.get("city") or org.get("city") or "").strip(),
                "state": (p.get("state") or org.get("state") or "").strip(),
                "industry": str(org.get("industry") or "")[:200],
                "employees": org.get("estimated_num_employees"),
            },
            "status": "pulled",
        })

    # Trim to batch size
    all_people = all_people[:batch_size]

    # Deduplicate by email
    seen_emails: set[str] = set()
    unique_leads: list[dict[str, Any]] = []
    for lead in all_people:
        email = lead["contact_email"]
        if email not in seen_emails:
            seen_emails.add(email)
            unique_leads.append(lead)

    # Check against existing CRM prospects to remove duplicates
    unique_leads = _dedupe_against_crm(unique_leads)

    inserted = _insert_leads(unique_leads)
    _update_run(run_id, {"leads_pulled": len(inserted)})
    return inserted


def _dedupe_against_crm(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove leads whose email or domain already exists in the prospects table."""
    if not leads:
        return leads
    domains = list({lead["domain"] for lead in leads if lead.get("domain")})
    existing_domains: set[str] = set()

    # Check in batches of 50
    for i in range(0, len(domains), 50):
        chunk = domains[i:i+50]
        domain_filter = ",".join(chunk)
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
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
            logger.warning("CRM dedupe check failed: %s", exc)

    return [lead for lead in leads if lead.get("domain", "").lower() not in existing_domains]


# ── Step 2: Clay Enrichment ──────────────────────────────────────────────

def step_clay_enrich(run_id: str, leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich leads via Clay API waterfall enrichment."""
    _update_run(run_id, {"current_step": "clay_enrichment"})

    if DRY_RUN or not CLAY_API_KEY:
        logger.info("ARIA pipeline: Clay dry run / no API key — skipping enrichment")
        for lead in leads:
            _update_lead(lead["id"], {
                "clay_enrichment": {"stub": True, "enriched": True},
                "status": "enriched",
            })
        _update_run(run_id, {"leads_enriched": len(leads)})
        return leads

    enriched_leads: list[dict[str, Any]] = []

    with httpx.Client(timeout=60.0) as client:
        for lead in leads:
            if _is_run_paused(run_id):
                break
            try:
                payload = {
                    "domain": lead.get("domain", ""),
                    "email": lead.get("contact_email", ""),
                    "name": lead.get("contact_name", ""),
                    "company": lead.get("company_name", ""),
                }
                r = client.post(
                    f"{CLAY_BASE}/enrich",
                    headers={
                        "Authorization": f"Bearer {CLAY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30.0,
                )
                if r.status_code < 300:
                    enrichment_data = r.json()
                    _update_lead(lead["id"], {
                        "clay_enrichment": enrichment_data,
                        "status": "enriched",
                    })
                    lead["clay_enrichment"] = enrichment_data
                    lead["status"] = "enriched"
                    enriched_leads.append(lead)
                else:
                    # Still keep lead even if enrichment fails
                    _update_lead(lead["id"], {
                        "clay_enrichment": {"error": r.text[:500]},
                        "status": "enriched",
                    })
                    lead["status"] = "enriched"
                    enriched_leads.append(lead)
            except Exception as exc:
                logger.warning("Clay enrichment failed for %s: %s", lead.get("domain"), exc)
                _update_lead(lead["id"], {
                    "clay_enrichment": {"error": str(exc)[:500]},
                    "status": "enriched",
                })
                lead["status"] = "enriched"
                enriched_leads.append(lead)

    _update_run(run_id, {"leads_enriched": len(enriched_leads)})
    return enriched_leads


# ── Step 3: ZeroBounce Verification ──────────────────────────────────────

def step_zerobounce_verify(run_id: str, leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Verify lead emails via ZeroBounce. Removes invalid emails."""
    from services.aria_prospect_pipeline import sync_prospect_zerobounce_chat

    _update_run(run_id, {"current_step": "zerobounce_verify"})

    if DRY_RUN or not ZEROBOUNCE_API_KEY:
        logger.info("ARIA pipeline: ZeroBounce dry run / no API key — marking all verified")
        for lead in leads:
            _update_lead(lead["id"], {
                "zero_bounce_result": {"stub": True, "status": "valid"},
                "status": "verified",
            })
            sync_prospect_zerobounce_chat(
                lead.get("domain", ""),
                zb_payload={"stub": True, "status": "valid"},
                zb_status="valid",
                pipeline_ok=True,
            )
        _update_run(run_id, {"leads_verified": len(leads)})
        return leads

    verified_leads: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0) as client:
        for lead in leads:
            if _is_run_paused(run_id):
                break
            email = lead.get("contact_email", "")
            if not email:
                _update_lead(lead["id"], {
                    "status": "removed",
                    "removed_reason": "no_email",
                })
                continue

            try:
                r = client.get(
                    ZEROBOUNCE_VALIDATE,
                    params={
                        "api_key": ZEROBOUNCE_API_KEY,
                        "email": email,
                        "ip_address": "",
                    },
                    timeout=15.0,
                )
                r.raise_for_status()
                zb_result = r.json()
                zb_status = (zb_result.get("status") or "").lower()

                _update_lead(lead["id"], {
                    "zero_bounce_result": zb_result,
                })

                # Keep valid and catch-all; remove invalid, disposable, etc.
                if zb_status in ("valid", "catch-all"):
                    _update_lead(lead["id"], {"status": "verified"})
                    lead["zero_bounce_result"] = zb_result
                    lead["status"] = "verified"
                    verified_leads.append(lead)
                    sync_prospect_zerobounce_chat(
                        lead.get("domain", ""),
                        zb_payload=zb_result,
                        zb_status=zb_status,
                        pipeline_ok=True,
                    )
                else:
                    _update_lead(lead["id"], {
                        "status": "removed",
                        "removed_reason": f"zerobounce_{zb_status}",
                    })
                    sync_prospect_zerobounce_chat(
                        lead.get("domain", ""),
                        zb_payload=zb_result,
                        zb_status=zb_status,
                        pipeline_ok=False,
                    )
            except Exception as exc:
                logger.warning("ZeroBounce failed for %s: %s", email, exc)
                # On error, keep the lead (benefit of the doubt)
                _update_lead(lead["id"], {
                    "zero_bounce_result": {"error": str(exc)[:500]},
                    "status": "verified",
                })
                lead["status"] = "verified"
                verified_leads.append(lead)
                sync_prospect_zerobounce_chat(
                    lead.get("domain", ""),
                    zb_payload={"error": str(exc)[:500]},
                    zb_status="unknown",
                    pipeline_ok=True,
                )

    _update_run(run_id, {"leads_verified": len(verified_leads)})
    return verified_leads


# ── Step 4: Hawk Domain Scan ─────────────────────────────────────────────

async def _scan_domain(client: httpx.AsyncClient, domain: str) -> dict[str, Any]:
    """Run Hawk scanner on a domain. Returns scan result with top vulnerability."""
    try:
        r = await client.post(
            f"{SCANNER_URL}/scan",
            json={"domain": domain, "mode": "fast"},
            timeout=SCAN_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        findings = data.get("findings") or []

        # Find the most critical vulnerability
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        top_finding = None
        for f in findings:
            sev = (f.get("severity") or "info").lower()
            if top_finding is None or severity_order.get(sev, 99) < severity_order.get(
                (top_finding.get("severity") or "info").lower(), 99
            ):
                top_finding = f

        vulnerability_text = ""
        if top_finding:
            title = top_finding.get("title") or top_finding.get("name") or ""
            interpretation = top_finding.get("interpretation") or top_finding.get("plain_english") or top_finding.get("description") or ""
            severity = (top_finding.get("severity") or "").upper()
            vulnerability_text = f"[{severity}] {title}"
            if interpretation:
                vulnerability_text += f" — {interpretation[:200]}"

        return {
            "score": data.get("score"),
            "findings_count": len(findings),
            "top_finding": top_finding,
            "vulnerability_text": vulnerability_text,
        }
    except Exception as exc:
        logger.warning("Hawk scan failed for %s: %s", domain, exc)
        return {"score": None, "findings_count": 0, "top_finding": None, "vulnerability_text": "", "error": str(exc)[:300]}


async def _scan_batch(domains_with_ids: list[tuple[str, str, str]]) -> dict[str, dict[str, Any]]:
    """Scan multiple domains concurrently. Returns {lead_id: scan_result}."""
    results: dict[str, dict[str, Any]] = {}
    semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)

    async def scan_one(lead_id: str, domain: str, client: httpx.AsyncClient) -> None:
        async with semaphore:
            result = await _scan_domain(client, domain)
            results[lead_id] = result

    async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as client:
        tasks = [scan_one(lid, dom, client) for lid, dom, _ in domains_with_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results


def step_hawk_scan(run_id: str, leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run Hawk domain scanner on each lead's domain."""
    from services.aria_prospect_pipeline import sync_prospect_scan_chat

    _update_run(run_id, {"current_step": "hawk_scan"})

    if DRY_RUN:
        logger.info("ARIA pipeline: Hawk scan dry run — generating stub findings")
        vulns_found = 0
        for i, lead in enumerate(leads):
            vuln = f"[HIGH] Missing SPF record — attackers can spoof emails from {lead.get('domain', 'unknown')}" if i % 2 == 0 else ""
            if vuln:
                vulns_found += 1
            _update_lead(lead["id"], {
                "vulnerability_found": vuln or None,
                "status": "scanned",
            })
            lead["vulnerability_found"] = vuln
            lead["status"] = "scanned"
            lead["hawk_score"] = 42
            sync_prospect_scan_chat(
                lead.get("domain", ""),
                vulnerability_text=vuln or None,
                vulnerability_type="HIGH" if vuln else None,
                hawk_score=42,
            )
        _update_run(run_id, {"leads_scanned": len(leads), "vulnerabilities_found": vulns_found})
        return leads

    # Build scan tasks
    domains_to_scan = [(lead["id"], lead.get("domain", ""), lead.get("contact_email", "")) for lead in leads if lead.get("domain")]

    # Run scans concurrently
    scan_results = asyncio.run(_scan_batch(domains_to_scan))

    vulns_found = 0
    scanned_leads: list[dict[str, Any]] = []
    for lead in leads:
        if _is_run_paused(run_id):
            break
        result = scan_results.get(lead["id"], {})
        vuln_text = result.get("vulnerability_text", "")
        top = result.get("top_finding") if isinstance(result.get("top_finding"), dict) else {}
        vuln_type = ""
        if isinstance(top, dict):
            vuln_type = str(top.get("severity") or top.get("type") or "")[:200]
        score = result.get("score")
        if score is not None:
            try:
                lead["hawk_score"] = max(0, min(100, int(score)))
            except (TypeError, ValueError):
                lead["hawk_score"] = None
        if vuln_text:
            vulns_found += 1

        _update_lead(lead["id"], {
            "vulnerability_found": vuln_text or None,
            "status": "scanned",
        })
        lead["vulnerability_found"] = vuln_text
        lead["status"] = "scanned"
        scanned_leads.append(lead)
        sync_prospect_scan_chat(
            lead.get("domain", ""),
            vulnerability_text=vuln_text or None,
            vulnerability_type=vuln_type or None,
            hawk_score=lead.get("hawk_score"),
        )

    _update_run(run_id, {"leads_scanned": len(scanned_leads), "vulnerabilities_found": vulns_found})
    return scanned_leads


# ── Step 5: OpenAI Personalized Email Generation ─────────────────────────

EMAIL_SYSTEM_PROMPT = """You are ARIA, the outbound email writer for Hawk Security — a US cybersecurity company serving small US professional practices.

Write a cold outreach email that is SHORT (under 100 words), direct, and personalized.

Structure:
- Subject line: "Found an open issue on [domain]" (or similar if no finding)
- Line 1: State the specific vulnerability in plain English
- Line 2: What an attacker could do with it (one sentence)
- Line 3: Brief offer to help
- CTA: Single booking link

Rules:
- No hyphens or dashes anywhere in the output
- No bullet points
- No greeting like "Dear" or "Hello"
- Use the contact's first name only
- Reference their exact domain
- If no vulnerability was found, use the US regulatory angle that matches the prospect's vertical:
    * dental / medical → HIPAA Security Rule + OCR breach notification (60-day rule, up to $2.1M/yr in civil monetary penalties)
    * accounting / CPA / tax → FTC Safeguards Rule + 30-day breach notification to the FTC (effective May 2024)
    * legal / law firm → ABA Formal Opinion 24-514 duty to notify clients of material data incidents (Model Rules 1.1, 1.4, 1.6)
- Never reference Canada, PIPEDA, CASL, or any Canadian-only regulation — this is a US market
- Keep it under 100 words total
- Sound human, not robotic

Return ONLY valid JSON: {"subject": "...", "body": "..."}
"""


# Vertical → (regulatory_angle, fallback_email_body_fragment)
_US_REGULATORY_ANGLE: dict[str, tuple[str, str]] = {
    "dental": (
        "HIPAA Security Rule compliance angle — OCR now requires breach notification within 60 days and civil penalties reach $2.1M per year",
        "Under the HIPAA Security Rule, US dental practices must protect PHI with MFA, encryption, and continuous monitoring. OCR breach enforcement is at record highs (Westend Dental paid $350K in Dec 2024).",
    ),
    "medical": (
        "HIPAA Security Rule compliance angle — OCR now requires breach notification within 60 days and civil penalties reach $2.1M per year",
        "Under the HIPAA Security Rule, US medical practices must protect PHI with MFA, encryption, and continuous monitoring. OCR breach enforcement is at record highs.",
    ),
    "accounting": (
        "FTC Safeguards Rule compliance angle — the May 2024 amendment requires 30-day breach notification and a written information security program (WISP)",
        "Under the amended FTC Safeguards Rule, US CPA and tax firms must maintain a written information security program (WISP), continuous external monitoring, and notify the FTC within 30 days of any breach affecting 500+ consumers.",
    ),
    "cpa": (
        "FTC Safeguards Rule compliance angle — the May 2024 amendment requires 30-day breach notification and a written information security program (WISP)",
        "Under the amended FTC Safeguards Rule, US CPA and tax firms must maintain a written information security program (WISP), continuous external monitoring, and notify the FTC within 30 days of any breach affecting 500+ consumers.",
    ),
    "tax": (
        "FTC Safeguards Rule compliance angle — the May 2024 amendment requires 30-day breach notification and a written information security program (WISP)",
        "Under the amended FTC Safeguards Rule, US tax preparers must maintain a written information security program (WISP), continuous external monitoring, and notify the FTC within 30 days of any breach affecting 500+ consumers.",
    ),
    "legal": (
        "ABA Formal Opinion 24-514 angle — lawyers have a duty under Model Rules 1.1, 1.4, and 1.6 to notify clients of material data incidents",
        "ABA Formal Opinion 24-514 confirms that US law firms have an ethical duty to notify clients of any material data incident affecting representation. Client-trust accounts and matter portals are the highest-value targets for wire-fraud diversion.",
    ),
    "law": (
        "ABA Formal Opinion 24-514 angle — lawyers have a duty under Model Rules 1.1, 1.4, and 1.6 to notify clients of material data incidents",
        "ABA Formal Opinion 24-514 confirms that US law firms have an ethical duty to notify clients of any material data incident affecting representation.",
    ),
}


def _regulatory_angle_for(vertical: str | None) -> tuple[str, str]:
    """Return (prompt_angle, fallback_body_fragment) for the given vertical."""
    v = (vertical or "").strip().lower()
    if v in _US_REGULATORY_ANGLE:
        return _US_REGULATORY_ANGLE[v]
    # Generic US fallback for unknown verticals
    return (
        "general US small-business cybersecurity posture angle — every US state has its own data-breach notification law and cyber-insurance carriers now require MFA + EDR + WISP at renewal",
        "Every US state has its own data-breach notification law and cyber-insurance carriers now require MFA, EDR, and a written information security program at renewal.",
    )


async def _generate_email_for_lead(lead: dict[str, Any]) -> dict[str, str]:
    """Generate personalized cold email for a single lead."""
    first_name = (lead.get("contact_name") or "").split()[0] if lead.get("contact_name") else "there"
    domain = lead.get("domain", "")
    company = lead.get("company_name", "")
    vulnerability = lead.get("vulnerability_found", "")
    # Inline fallback — CAL_COM_BOOKING_URL defaults to "" in config so the outbound
    # cold-email template never emits a bare empty href/link when the env var is
    # unset in prod.
    booking_url = CAL_COM_BOOKING_URL or "https://cal.com/hawksecurity/15min"

    if vulnerability:
        user_msg = f"""Generate a cold email for:
- First name: {first_name}
- Company: {company}
- Domain: {domain}
- Vulnerability found: {vulnerability}
- Booking link: {booking_url}"""
    else:
        prompt_angle, _ = _regulatory_angle_for(lead.get("vertical"))
        user_msg = f"""Generate a cold email for:
- First name: {first_name}
- Company: {company}
- Domain: {domain}
- No specific vulnerability found. Use this angle: {prompt_angle}.
- Booking link: {booking_url}"""

    try:
        raw = await chat_text_async(
            api_key=OPENAI_API_KEY,
            user_messages=[{"role": "user", "content": user_msg}],
            max_tokens=500,
            system=EMAIL_SYSTEM_PROMPT,
            model=OPENAI_MODEL,
        )

        # Parse JSON from response
        parsed = _parse_email_json(raw)
        if parsed:
            return parsed

        return {"subject": f"Found an open issue on {domain}", "body": raw[:500]}
    except Exception as exc:
        logger.warning("OpenAI email generation failed for %s: %s", domain, exc)
        # Fallback template
        if vulnerability:
            return {
                "subject": f"Found an open issue on {domain}",
                "body": f"{first_name},\n\nWe ran a security scan on {domain} and found: {vulnerability[:150]}.\n\nThis means an attacker could potentially exploit this to gain access to your systems or data.\n\nWe found additional issues as well. I would love to walk you through what we found in 15 minutes.\n\n{booking_url}",
            }
        _, fallback_fragment = _regulatory_angle_for(lead.get("vertical"))
        return {
            "subject": f"Quick security question about {domain}",
            "body": f"{first_name},\n\n{fallback_fragment} We ran a quick check on {domain} and wanted to share what we found.\n\nWould you have 15 minutes this week?\n\n{booking_url}",
        }


def _parse_email_json(raw: str) -> dict[str, str] | None:
    """Parse JSON email from OpenAI response."""
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    subj, body = data.get("subject"), data.get("body")
    if not isinstance(subj, str) or not isinstance(body, str):
        return None
    return {"subject": subj.strip(), "body": body.strip()}


async def _generate_emails_batch(leads: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Generate emails for a batch of leads concurrently."""
    results: dict[str, dict[str, str]] = {}
    semaphore = asyncio.Semaphore(5)  # Rate limit OpenAI calls

    async def gen_one(lead: dict[str, Any]) -> None:
        async with semaphore:
            email = await _generate_email_for_lead(lead)
            results[lead["id"]] = email

    tasks = [gen_one(lead) for lead in leads]
    await asyncio.gather(*tasks, return_exceptions=True)
    return results


def step_generate_emails(run_id: str, leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate personalized cold emails for each lead via OpenAI."""
    from services.aria_prospect_pipeline import sync_prospect_email_ready_chat

    _update_run(run_id, {"current_step": "email_generation"})

    if DRY_RUN or not OPENAI_API_KEY:
        logger.info("ARIA pipeline: Email generation dry run — using templates")
        # Same fallback as above — dry-run templates need a real URL too.
        booking_url = CAL_COM_BOOKING_URL or "https://cal.com/hawksecurity/15min"
        for lead in leads:
            first_name = (lead.get("contact_name") or "").split()[0] if lead.get("contact_name") else "there"
            domain = lead.get("domain", "")
            vuln = lead.get("vulnerability_found", "")
            if vuln:
                email = {
                    "subject": f"Found an open issue on {domain}",
                    "body": f"{first_name},\n\nWe scanned {domain} and found: {vuln[:100]}.\n\nThis could allow attackers to access your systems.\n\nCan we walk you through it in 15 minutes?\n\n{booking_url}",
                }
            else:
                _, fallback_fragment = _regulatory_angle_for(lead.get("vertical"))
                email = {
                    "subject": f"Quick security question about {domain}",
                    "body": f"{first_name},\n\n{fallback_fragment} We checked {domain} and have findings to share.\n\n15 minutes this week?\n\n{booking_url}",
                }
            _update_lead(lead["id"], {
                "email_subject": email["subject"],
                "email_content": email["body"],
                "status": "email_generated",
            })
            lead["email_subject"] = email["subject"]
            lead["email_content"] = email["body"]
            lead["status"] = "email_generated"
            sync_prospect_email_ready_chat(lead.get("domain", ""), email["subject"], email["body"])
        _update_run(run_id, {"emails_generated": len(leads)})
        return leads

    email_results = asyncio.run(_generate_emails_batch(leads))

    generated_count = 0
    for lead in leads:
        if _is_run_paused(run_id):
            break
        email = email_results.get(lead["id"], {})
        subject = email.get("subject", "")
        body = email.get("body", "")
        if subject and body:
            _update_lead(lead["id"], {
                "email_subject": subject,
                "email_content": body,
                "status": "email_generated",
            })
            lead["email_subject"] = subject
            lead["email_content"] = body
            lead["status"] = "email_generated"
            generated_count += 1
            sync_prospect_email_ready_chat(lead.get("domain", ""), subject, body)
        else:
            _update_lead(lead["id"], {
                "status": "removed",
                "removed_reason": "email_generation_failed",
            })

    _update_run(run_id, {"emails_generated": generated_count})
    return [l for l in leads if l.get("status") == "email_generated"]


# ── Step 6: Smartlead Loading ────────────────────────────────────────────

def step_smartlead_load(run_id: str, leads: list[dict[str, Any]], vertical: str) -> list[dict[str, Any]]:
    """Load leads with personalized emails into Smartlead campaign."""
    from services.aria_prospect_pipeline import sync_prospect_smartlead_chat

    _update_run(run_id, {"current_step": "smartlead_load"})

    if DRY_RUN or not SMARTLEAD_API_KEY:
        logger.info("ARIA pipeline: Smartlead dry run / no API key — skipping upload")
        for lead in leads:
            _update_lead(lead["id"], {
                "email_sent": True,
                "smartlead_campaign_id": "dry_run_campaign",
                "status": "sent",
            })
            lead["email_sent"] = True
            lead["status"] = "sent"
            sync_prospect_smartlead_chat(lead.get("domain", ""), "dry_run_campaign")
        _update_run(run_id, {"emails_sent": len(leads)})
        return leads

    # Get or create campaign for this vertical
    campaign_id = _get_or_create_smartlead_campaign(vertical)
    if not campaign_id:
        logger.error("Failed to get/create Smartlead campaign for %s", vertical)
        _update_run(run_id, {"emails_sent": 0})
        return leads

    sent_count = 0
    with httpx.Client(timeout=30.0) as client:
        for lead in leads:
            if _is_run_paused(run_id):
                break
            try:
                # Build Smartlead lead payload
                apollo_data = lead.get("apollo_data") or {}
                payload = {
                    "lead_list": [{
                        "email": lead.get("contact_email", ""),
                        "first_name": (lead.get("contact_name") or "").split()[0] if lead.get("contact_name") else "",
                        "last_name": " ".join((lead.get("contact_name") or "").split()[1:]) if lead.get("contact_name") else "",
                        "company_name": lead.get("company_name", ""),
                        "custom_fields": {
                            "domain": lead.get("domain", ""),
                            "email_subject": lead.get("email_subject", ""),
                            "email_body": lead.get("email_content", ""),
                            "vulnerability": lead.get("vulnerability_found", ""),
                        },
                    }],
                    "settings": {
                        "ignore_global_block_list": False,
                        "ignore_unsubscribe_list": False,
                    },
                }

                r = client.post(
                    f"{SMARTLEAD_BASE}/campaigns/{campaign_id}/leads",
                    params={"api_key": SMARTLEAD_API_KEY},
                    json=payload,
                    timeout=30.0,
                )

                if r.status_code < 300:
                    _update_lead(lead["id"], {
                        "email_sent": True,
                        "smartlead_campaign_id": campaign_id,
                        "status": "sent",
                    })
                    lead["email_sent"] = True
                    lead["smartlead_campaign_id"] = campaign_id
                    lead["status"] = "sent"
                    sent_count += 1
                    sync_prospect_smartlead_chat(lead.get("domain", ""), str(campaign_id))
                else:
                    logger.warning("Smartlead upload failed for %s: %s", lead.get("contact_email"), r.text[:300])
            except Exception as exc:
                logger.warning("Smartlead upload error for %s: %s", lead.get("contact_email"), exc)

    _update_run(run_id, {"emails_sent": sent_count})
    return leads


def _get_or_create_smartlead_campaign(vertical: str) -> str | None:
    """Get existing Smartlead campaign for vertical or create one."""
    campaign_name = f"ARIA - {vertical.title()} Outbound"
    try:
        with httpx.Client(timeout=30.0) as client:
            # List campaigns to find existing
            r = client.get(
                f"{SMARTLEAD_BASE}/campaigns",
                params={"api_key": SMARTLEAD_API_KEY, "limit": "100"},
                timeout=30.0,
            )
            if r.status_code < 300:
                campaigns = r.json()
                if isinstance(campaigns, list):
                    for c in campaigns:
                        if c.get("name") == campaign_name:
                            return str(c.get("id", ""))

            # Create new campaign
            r = client.post(
                f"{SMARTLEAD_BASE}/campaigns/create",
                params={"api_key": SMARTLEAD_API_KEY},
                json={"name": campaign_name},
                timeout=30.0,
            )
            if r.status_code < 300:
                data = r.json()
                return str(data.get("id", ""))
    except Exception as exc:
        logger.exception("Smartlead campaign creation failed: %s", exc)
    return None


# ── Full Pipeline Orchestrator ───────────────────────────────────────────

def _check_inventory_for_ready_leads(
    vertical: str,
    location: str,
    batch_size: int,
) -> list[dict[str, Any]]:
    """
    Check aria_lead_inventory for ready leads matching vertical + location.

    Returns matching leads or empty list if inventory is empty for this combo.
    This enables chat-triggered pipeline to be instant when inventory has pre-built leads.
    """
    if not SUPABASE_URL:
        return []

    try:
        from services.aria_lead_inventory import get_ready_leads

        leads = get_ready_leads(vertical=vertical, city=location, limit=batch_size)
        if not leads:
            return []

        logger.info(
            "Inventory hit: %d ready leads for %s in %s",
            len(leads),
            vertical,
            location,
        )
        return leads
    except Exception as exc:
        logger.warning("Inventory check failed (falling back to on-demand): %s", exc)
        return []


def _load_inventory_leads_to_pipeline(
    run_id: str,
    inventory_leads: list[dict[str, Any]],
    vertical: str,
) -> dict[str, Any]:
    """
    Take pre-built leads from inventory and load them into the on-demand pipeline
    (skip Apollo, Clay, ZeroBounce, scan, email gen — all already done in nightly).
    Just loads into Smartlead and marks dispatched.
    """
    # Insert into pipeline leads table for tracking
    pipeline_leads = []
    for inv in inventory_leads:
        pipeline_leads.append({
            "run_id": run_id,
            "company_name": inv.get("business_name") or inv.get("company_name") or "",
            "domain": inv.get("domain") or "",
            "contact_name": inv.get("contact_name") or "",
            "contact_email": inv.get("contact_email") or "",
            "vertical": vertical,
            "apollo_data": {"source": "inventory", "inventory_id": inv.get("id")},
            "vulnerability_found": inv.get("vulnerability_found"),
            "email_subject": inv.get("email_subject"),
            "email_content": inv.get("email_body"),
            "status": "email_generated",
        })

    inserted = _insert_leads(pipeline_leads)
    _update_run(run_id, {
        "leads_pulled": len(inserted),
        "leads_enriched": len(inserted),
        "leads_verified": len(inserted),
        "leads_scanned": len(inserted),
        "emails_generated": len(inserted),
        "current_step": "smartlead_load",
    })

    # Load into Smartlead
    step_smartlead_load(run_id, inserted, vertical)

    # Mark inventory leads as dispatched
    try:
        from services.aria_lead_inventory import mark_leads_dispatched
        inventory_ids = [inv["id"] for inv in inventory_leads if inv.get("id")]
        if inventory_ids:
            mark_leads_dispatched(inventory_ids, campaign_id="chat_dispatch")
    except Exception as exc:
        logger.warning("Failed to mark inventory leads dispatched: %s", exc)

    _update_run(run_id, {
        "status": "completed",
        "current_step": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    return _build_summary(run_id)


def step_apify_discover(
    run_id: str,
    vertical: str,
    location: str,
    batch_size: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Discover leads and find emails via Apify 4-actor pipeline (on-demand).

    Runs Google Maps scraper → LinkedIn → Leads Finder → Website Crawler
    for a single city + vertical.  Falls back to Apollo as absolute last resort.

    Returns ``(inserted_leads, error_message)``. On success ``error_message`` is None.
    On failure the list is empty and ``error_message`` is a user-facing explanation.
    """
    _update_run(run_id, {"current_step": "apify_discover"})

    try:
        from services.aria_apify_scraper import (
            format_discovery_empty_message,
            run_ondemand_discovery,
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                run_ondemand_discovery(vertical, location, batch_size, pipeline_run_id=run_id),
            )
            raw_leads, discover_meta = future.result(timeout=900)

        if not raw_leads:
            logger.info(
                "On-demand discovery returned 0 leads for %s in %s meta=%s",
                vertical,
                location,
                discover_meta,
            )
            return [], format_discovery_empty_message(discover_meta)

        # Filter: only leads with emails
        leads_with_email = [ld for ld in raw_leads if ld.get("contact_email")]
        if not leads_with_email:
            logger.info(
                "Discovery found businesses but none with email for %s in %s meta=%s",
                vertical,
                location,
                discover_meta,
            )
            return [], format_discovery_empty_message(discover_meta)

        # Map to pipeline_leads format
        pipeline_leads: list[dict[str, Any]] = []
        for ld in leads_with_email:
            pipeline_leads.append({
                "run_id": run_id,
                "company_name": ld.get("business_name") or "",
                "domain": ld.get("domain") or "",
                "contact_name": ld.get("contact_name") or "",
                "contact_email": ld.get("contact_email") or "",
                "vertical": vertical,
                "apollo_data": {
                    "source": ld.get("email_finder", "apify"),
                    "google_place_id": ld.get("google_place_id"),
                    "google_rating": ld.get("google_rating"),
                    "review_count": ld.get("review_count"),
                    "city": ld.get("city"),
                    "province": ld.get("province"),
                    "address": ld.get("address"),
                    "lead_score": ld.get("lead_score"),
                },
                "status": "enriched",
            })

        inserted = _insert_leads(pipeline_leads)
        _update_run(run_id, {
            "leads_pulled": len(inserted),
            "leads_enriched": len(inserted),
        })
        return inserted, None

    except Exception as exc:
        logger.exception("Apify discovery failed: %s", exc)
        # Fall back to Apollo as absolute last resort
        logger.info("Falling back to Apollo after Apify error")
        apollo_leads = step_apollo_pull(run_id, vertical, location, batch_size)
        if apollo_leads:
            return apollo_leads, None
        return [], (
            f"Discovery failed: {str(exc)[:500]}. Apollo fallback also returned no leads."
        )


def run_outbound_pipeline(
    run_id: str,
    vertical: str,
    location: str,
    batch_size: int = 50,
) -> dict[str, Any]:
    """
    Execute the full ARIA outbound pipeline end-to-end.

    First checks aria_lead_inventory for ready leads matching the vertical + location.
    If inventory has leads, uses those directly (instant dispatch).
    Falls back to on-demand discovery via Google Places (with Apollo as second fallback)
    → Prospeo/Apollo email finding → ZeroBounce → scan → email gen → Smartlead.

    Returns a summary dict suitable for chat display.
    """
    try:
        # Try inventory first (instant path)
        inventory_leads = _check_inventory_for_ready_leads(vertical, location, batch_size)
        if inventory_leads:
            _update_run(run_id, {"current_step": "inventory_dispatch"})
            return _load_inventory_leads_to_pipeline(run_id, inventory_leads, vertical)

        # Fallback: on-demand discovery via Apify 4-actor pipeline
        # Step 1: Apify Discovery (Google Maps + LinkedIn + Leads Finder + Website Crawler)
        # Leads come back with emails already found by actors 2-4
        leads, discover_err = step_apify_discover(run_id, vertical, location, batch_size)
        if not leads:
            _update_run(run_id, {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": discover_err or "No leads found for this vertical and location.",
            })
            return _build_summary(run_id)

        if _is_run_paused(run_id):
            return _build_summary(run_id)

        # Step 2: ZeroBounce Verification
        leads = step_zerobounce_verify(run_id, leads)
        if not leads:
            _update_run(run_id, {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": "All leads removed during email verification.",
            })
            return _build_summary(run_id)
        if _is_run_paused(run_id):
            return _build_summary(run_id)

        # Step 3: Hawk Domain Scan
        leads = step_hawk_scan(run_id, leads)
        if _is_run_paused(run_id):
            return _build_summary(run_id)

        # Step 4: Generate Personalized Emails
        leads = step_generate_emails(run_id, leads)
        if not leads:
            _update_run(run_id, {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": "Email generation failed for all leads.",
            })
            return _build_summary(run_id)
        if _is_run_paused(run_id):
            return _build_summary(run_id)

        # Step 5: Load into Smartlead
        step_smartlead_load(run_id, leads, vertical)

        # Mark complete
        _update_run(run_id, {
            "status": "completed",
            "current_step": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        return _build_summary(run_id)

    except Exception as exc:
        logger.exception("ARIA pipeline failed for run %s: %s", run_id, exc)
        _update_run(run_id, {
            "status": "failed",
            "error_message": str(exc)[:1000],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        return _build_summary(run_id)


def _build_summary(run_id: str) -> dict[str, Any]:
    """Build a pipeline run summary for chat display."""
    run = _get_run(run_id)
    if not run:
        return {"error": "Run not found", "run_id": run_id}

    return {
        "run_id": run_id,
        "vertical": run.get("vertical", ""),
        "location": run.get("location", ""),
        "status": run.get("status", ""),
        "current_step": run.get("current_step", ""),
        "leads_pulled": run.get("leads_pulled", 0),
        "leads_enriched": run.get("leads_enriched", 0),
        "leads_verified": run.get("leads_verified", 0),
        "leads_scanned": run.get("leads_scanned", 0),
        "emails_generated": run.get("emails_generated", 0),
        "emails_sent": run.get("emails_sent", 0),
        "vulnerabilities_found": run.get("vulnerabilities_found", 0),
        "error_message": run.get("error_message"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
    }


def pause_pipeline(run_id: str) -> dict[str, Any]:
    """Pause a running pipeline."""
    run = _get_run(run_id)
    if not run:
        return {"error": "Run not found"}
    if run.get("status") != "running":
        return {"error": f"Cannot pause — run status is {run.get('status')}"}
    _update_run(run_id, {"status": "paused"})
    return {"paused": True, "run_id": run_id}


def resume_pipeline(run_id: str, uid: str) -> dict[str, Any]:
    """Resume a paused pipeline from the current step."""
    run = _get_run(run_id)
    if not run:
        return {"error": "Run not found"}
    if run.get("status") != "paused":
        return {"error": f"Cannot resume — run status is {run.get('status')}"}

    _update_run(run_id, {"status": "running"})

    current_step = run.get("current_step", "")
    vertical = run.get("vertical", "dental")
    location = run.get("location", "")

    try:
        # Get leads at the current stage and resume from there
        if current_step in ("apify_discover", "apollo_pull", "email_finding"):
            leads = _get_run_leads(run_id, "pulled") or _get_run_leads(run_id, "enriched")
            if not leads:
                leads, _disc_err = step_apify_discover(
                    run_id, vertical, location, run.get("batch_size", 50)
                )
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            leads = step_zerobounce_verify(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            leads = step_hawk_scan(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            leads = step_generate_emails(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            step_smartlead_load(run_id, leads, vertical)
        elif current_step == "zerobounce_verify":
            leads = _get_run_leads(run_id, "enriched")
            leads = step_zerobounce_verify(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            leads = step_hawk_scan(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            leads = step_generate_emails(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            step_smartlead_load(run_id, leads, vertical)
        elif current_step == "hawk_scan":
            leads = _get_run_leads(run_id, "verified")
            leads = step_hawk_scan(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            leads = step_generate_emails(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            step_smartlead_load(run_id, leads, vertical)
        elif current_step == "email_generation":
            leads = _get_run_leads(run_id, "scanned")
            leads = step_generate_emails(run_id, leads)
            if _is_run_paused(run_id):
                return _build_summary(run_id)
            step_smartlead_load(run_id, leads, vertical)
        elif current_step == "smartlead_load":
            leads = _get_run_leads(run_id, "email_generated")
            step_smartlead_load(run_id, leads, vertical)

        _update_run(run_id, {
            "status": "completed",
            "current_step": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as exc:
        logger.exception("ARIA pipeline resume failed for run %s: %s", run_id, exc)
        _update_run(run_id, {
            "status": "failed",
            "error_message": str(exc)[:1000],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    return _build_summary(run_id)
