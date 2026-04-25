"""
Charlotte daily automation: Apollo → ZeroBounce → suppressions / CRM dedupe → Scanner → OpenAI → Smartlead → Supabase log → CEO WhatsApp.

Triggered by POST /api/crm/cron/charlotte-run (X-Cron-Secret).
Set CHARLOTTE_AUTOMATION_DRY_RUN=1 to skip external APIs (smoke test structure only).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import zoneinfo
from datetime import date, datetime
from typing import Any

import httpx

from config import OPENAI_MODEL

from services.openai_chat import chat_text_async

logger = logging.getLogger(__name__)

MST = zoneinfo.ZoneInfo("America/Edmonton")
SCANNER_URL = os.environ.get("SCANNER_URL", "https://intelligent-rejoicing-production.up.railway.app").rstrip("/")
APOLLO_BASE = os.environ.get("APOLLO_API_BASE", "https://api.apollo.io/api/v1").rstrip("/")
SMARTLEAD_BASE = os.environ.get("SMARTLEAD_API_BASE", "https://server.smartlead.ai/api/v1").rstrip("/")
ZEROBOUNCE_VALIDATE = "https://api.zerobounce.net/v2/validate"

CHARLOTTE_OPENAI_MODEL = (
    os.environ.get("CHARLOTTE_OPENAI_MODEL", "").strip() or OPENAI_MODEL
)
SCAN_TIMEOUT = 120.0
MAX_TOKENS = 500
SCAN_CONCURRENCY = 10

# Rotating verticals (index 0..6 stored in crm_settings charlotte_industry_day_index)
INDUSTRY_DAYS: list[dict[str, Any]] = [
    {
        "label": "Dental Clinics",
        "keywords": ["dental", "dentistry", "dental clinic"],
        "titles": [
            "dentist",
            "dental office manager",
            "clinic owner",
            "owner",
            "principal",
            "managing partner",
            "director",
            "CEO",
            "founder",
        ],
    },
    {
        "label": "Law Firms",
        "keywords": ["law firm", "legal services", "lawyer"],
        "titles": [
            "lawyer",
            "solicitor",
            "managing partner",
            "law firm owner",
            "owner",
            "principal",
            "director",
            "CEO",
            "founder",
        ],
    },
    {
        "label": "Accounting Firms",
        "keywords": ["accounting", "CPA", "bookkeeping"],
        "titles": [
            "CPA",
            "accountant",
            "accounting firm owner",
            "owner",
            "principal",
            "managing partner",
            "director",
            "CEO",
            "founder",
        ],
    },
    {
        "label": "Financial Advisors",
        "keywords": ["financial advisor", "wealth management", "financial planning"],
        "titles": [
            "owner",
            "principal",
            "managing partner",
            "director",
            "CEO",
            "founder",
            "financial advisor",
            "wealth advisor",
        ],
    },
    {
        "label": "Medical Clinics",
        "keywords": ["medical clinic", "health clinic", "physician"],
        "titles": [
            "owner",
            "principal",
            "managing partner",
            "director",
            "CEO",
            "founder",
            "physician",
            "clinic owner",
        ],
    },
    {
        "label": "Physiotherapy",
        "keywords": ["physiotherapy", "physical therapy", "rehabilitation"],
        "titles": [
            "owner",
            "principal",
            "physiotherapist",
            "clinic owner",
            "director",
            "CEO",
            "founder",
        ],
    },
    {
        "label": "Optometry",
        "keywords": ["optometry", "optometrist", "eye care"],
        "titles": [
            "optometrist",
            "owner",
            "clinic owner",
            "principal",
            "director",
            "CEO",
            "founder",
        ],
    },
]

SEVERITY_ORDER = ("critical", "high", "medium", "warning", "low", "info", "ok")


def _sb_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _normalize_domain(raw: str) -> str:
    d = (raw or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p) :]
    d = d.split("/")[0].split("?")[0].strip()
    if "@" in d:
        d = d.split("@")[-1]
    if d.startswith("www."):
        d = d[4:]
    return d


def _rank_sev(s: str) -> int:
    s = (s or "low").lower()
    try:
        return SEVERITY_ORDER.index(s)
    except ValueError:
        return 99


def _finding_plain(f: dict[str, Any]) -> str:
    for k in ("interpretation", "plain_english", "description", "title"):
        v = f.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _breach_info(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        layer = str(f.get("layer") or "").lower()
        title = str(f.get("title") or "").lower()
        cat = str(f.get("category") or "").lower()
        blob = f"{layer} {title} {cat}"
        if any(x in blob for x in ("breach", "hibp", "stealer", "credential", "pwned")):
            return True, (_finding_plain(f) or title)[:500]
    return False, ""


def _begin_charlotte_run_row(supabase_url: str, industry: str | None) -> str | None:
    run_d = date.today()
    try:
        run_d = datetime.now(MST).date()
    except Exception:
        pass
    body = {
        "run_date": str(run_d),
        "industry": industry,
        "leads_pulled": 0,
        "emails_verified": 0,
        "emails_suppressed": 0,
        "domains_scanned": 0,
        "scan_failures": 0,
        "scan_skipped": 0,
        "email_failed": 0,
        "upload_failed": 0,
        "emails_written": 0,
        "leads_uploaded": 0,
    }
    try:
        r = httpx.post(
            f"{supabase_url}/rest/v1/charlotte_runs",
            headers=_sb_headers(),
            json=body,
            timeout=25.0,
        )
        r.raise_for_status()
        rows = r.json()
        if isinstance(rows, list) and rows:
            return str(rows[0].get("id") or "")
    except Exception as e:
        logger.exception("begin charlotte_runs: %s", e)
    return None


def _finalize_charlotte_run(supabase_url: str, run_id: str | None, stats: dict[str, Any]) -> None:
    if not run_id:
        return
    patch = {
        "leads_pulled": stats.get("leads_pulled", 0),
        "emails_verified": stats.get("emails_verified", 0),
        "emails_suppressed": stats.get("emails_suppressed", 0),
        "domains_scanned": stats.get("domains_scanned", 0),
        "scan_failures": stats.get("scan_failures", 0),
        "scan_skipped": stats.get("scan_skipped", 0),
        "email_failed": stats.get("email_failed", 0),
        "upload_failed": stats.get("upload_failed", 0),
        "emails_written": stats.get("emails_written", 0),
        "leads_uploaded": stats.get("leads_uploaded", 0),
    }
    try:
        httpx.patch(
            f"{supabase_url}/rest/v1/charlotte_runs",
            headers=_sb_headers(),
            params={"id": f"eq.{run_id}"},
            json=patch,
            timeout=25.0,
        ).raise_for_status()
    except Exception as e:
        logger.exception("finalize charlotte_runs: %s", e)


def _insert_charlotte_email_row(
    supabase_url: str,
    *,
    run_id: str | None,
    row: dict[str, Any],
    scan: dict[str, Any],
    email_body: dict[str, str],
    smartlead_lead_id: str | None,
) -> None:
    findings_raw = scan.get("findings") or []
    findings = [dict(f) for f in findings_raw if isinstance(f, dict)]
    findings.sort(key=lambda x: _rank_sev(str(x.get("severity", ""))))
    top_plain = _finding_plain(findings[0]) if findings else ""
    body = email_body.get("body") or ""
    subj = email_body.get("subject") or ""
    wc = len(body.split()) if body else 0
    has_dash = "-" in body or "-" in subj
    has_bul = "•" in body or "\n1." in body or "\n- " in body
    dom = row.get("domain") or ""
    score_v = scan.get("score")
    payload = {
        "run_id": run_id,
        "prospect_domain": dom,
        "prospect_email": row.get("email"),
        "prospect_industry": (row.get("industry") or "")[:500],
        "hawk_score": int(score_v) if score_v is not None else None,
        "top_finding": (top_plain or "")[:4000],
        "email_subject": subj[:2000],
        "email_body": body[:16000],
        "word_count": wc,
        "has_dashes": has_dash,
        "has_bullets": has_bul,
        "contains_domain": dom.lower() in body.lower() or dom.lower() in subj.lower(),
        "contains_score": (str(score_v) in body or str(score_v) in subj) if score_v is not None else False,
        "smartlead_lead_id": smartlead_lead_id,
    }
    try:
        httpx.post(
            f"{supabase_url}/rest/v1/charlotte_emails",
            headers=_sb_headers(),
            json=payload,
            timeout=20.0,
        ).raise_for_status()
    except Exception as e:
        logger.exception("charlotte_emails insert: %s", e)


def _validate_email_content(
    email_body: dict[str, str],
    row: dict[str, Any],
    scan: dict[str, Any],
) -> bool:
    subj = (email_body.get("subject") or "").strip()
    body = (email_body.get("body") or "").strip()
    if not subj or not body:
        return False
    if len(body.split()) > 150:
        return False
    if "-" in body or "-" in subj:
        return False
    fn = (row.get("first_name") or "").strip()
    dom = (row.get("domain") or "").strip().lower()
    if fn and fn.lower() not in body.lower():
        return False
    if dom and dom not in body.lower() and dom not in subj.lower():
        return False
    score = scan.get("score")
    if score is not None and str(int(score)) not in body and str(int(score)) not in subj:
        return False
    findings_raw = scan.get("findings") or []
    findings = [dict(f) for f in findings_raw if isinstance(f, dict)]
    if not findings:
        return "no major" in body.lower() or "finding" in body.lower()
    hit = False
    for f in findings[:8]:
        plain = _finding_plain(f)
        if plain and len(plain) > 12 and plain[:24].lower() in body.lower():
            hit = True
            break
        t = str(f.get("title") or "")
        if len(t) > 8 and t[:20].lower() in body.lower():
            hit = True
            break
    return hit


def _sanitize_no_hyphens(text: str) -> str:
    if not text:
        return text
    t = text.replace("—", ",").replace("–", ",")
    t = re.sub(r"\s*-\s*", ", ", t)
    t = re.sub(r",\s*,+", ", ", t)
    return t.strip()


def _parse_claude_json(text: str) -> dict[str, str] | None:
    raw = text.strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    sub, body = data.get("subject"), data.get("body")
    if not isinstance(sub, str) or not isinstance(body, str):
        return None
    return {"subject": sub.strip().lower(), "body": body.strip()}


def _get_setting(supabase_url: str, key: str, default: str = "0") -> str:
    r = httpx.get(
        f"{supabase_url}/rest/v1/crm_settings",
        headers=_sb_headers(),
        params={"key": f"eq.{key}", "select": "value", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    if rows:
        return str(rows[0].get("value") or default)
    httpx.post(
        f"{supabase_url}/rest/v1/crm_settings",
        headers=_sb_headers(),
        json={"key": key, "value": default},
        timeout=15.0,
    )
    return default


def _set_setting(supabase_url: str, key: str, value: str) -> None:
    chk = httpx.get(
        f"{supabase_url}/rest/v1/crm_settings",
        headers=_sb_headers(),
        params={"key": f"eq.{key}", "select": "key", "limit": "1"},
        timeout=15.0,
    )
    chk.raise_for_status()
    if chk.json():
        httpx.patch(
            f"{supabase_url}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": f"eq.{key}"},
            json={"value": value},
            timeout=15.0,
        ).raise_for_status()
    else:
        httpx.post(
            f"{supabase_url}/rest/v1/crm_settings",
            headers=_sb_headers(),
            json={"key": key, "value": value},
            timeout=15.0,
        ).raise_for_status()


def _apollo_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": os.environ.get("APOLLO_API_KEY", "").strip(),
    }


def _map_apollo_person(p: dict[str, Any]) -> dict[str, Any]:
    org = p.get("organization") or {}
    if isinstance(org, str):
        org = {}
    email = (p.get("email") or p.get("primary_email") or "").strip()
    # ``mixed_people/api_search`` returns locked emails as the string
    # ``email_not_unlocked@domain_not_unlocked.com`` (truthy but unusable).
    # Treat those as empty so the downstream bulk_match step unlocks them.
    if "email_not_unlocked" in email.lower():
        email = ""
    website = (
        org.get("website_url")
        or org.get("primary_domain")
        or p.get("organization_website_url")
        or ""
    )
    city = p.get("city") or org.get("city") or ""
    state = p.get("state") or org.get("state") or ""
    industry = org.get("industry") or org.get("keyword_tags") or ""
    if isinstance(industry, list):
        industry = ", ".join(str(x) for x in industry[:5])
    return {
        "apollo_person_id": p.get("id"),
        "first_name": (p.get("first_name") or "").strip(),
        "last_name": (p.get("last_name") or "").strip(),
        "email": email,
        "company": (org.get("name") or "").strip(),
        "website": str(website).strip(),
        "phone": str(org.get("primary_phone") or "").strip(),
        "city": str(city).strip(),
        "state": str(state).strip(),
        "industry": str(industry)[:200] if industry else "",
        "_raw_person": p,
    }


def _apollo_search_page(
    client: httpx.Client, industry: dict[str, Any], page: int, per_page: int
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "page": page,
        "per_page": per_page,
        "person_titles": industry["titles"],
        "person_locations": ["United States"],
        "organization_num_employees_ranges": ["1,50"],
        "contact_email_status": ["verified", "unverified"],
        "organization_industry_tag_ids": [],
        "q_organization_keyword_tags": industry["keywords"][:5],
    }
    r = client.post(
        f"{APOLLO_BASE}/mixed_people/api_search",
        headers=_apollo_headers(),
        json=body,
        timeout=120.0,
    )
    r.raise_for_status()
    data = r.json()
    people = data.get("people") or data.get("contacts") or []
    out = []
    for p in people:
        if not isinstance(p, dict):
            continue
        out.append(_map_apollo_person(p))
    return out


def _apollo_bulk_match_emails(client: httpx.Client, people: list[dict[str, Any]]) -> None:
    """Mutates people rows in place with email from bulk_match."""
    need = [p for p in people if not p.get("email") and p.get("_raw_person", {}).get("id")]
    for i in range(0, len(need), 10):
        chunk = need[i : i + 10]
        ids = [str(p["_raw_person"]["id"]) for p in chunk]
        payload = {
            "reveal_personal_emails": True,
            "details": [{"id": pid} for pid in ids],
        }
        r = client.post(
            f"{APOLLO_BASE}/people/bulk_match",
            headers=_apollo_headers(),
            json=payload,
            timeout=120.0,
        )
        if r.status_code >= 400:
            logger.warning("Apollo bulk_match failed: %s %s", r.status_code, r.text[:400])
            continue
        data = r.json()
        matches = data.get("matches") or data.get("people") or []
        # Response shape varies; map by id
        by_id = {}
        for m in matches:
            if isinstance(m, dict) and m.get("id"):
                by_id[str(m["id"])] = m
        for p in chunk:
            pid = str(p["_raw_person"].get("id", ""))
            m = by_id.get(pid)
            if not m:
                continue
            em = (m.get("email") or m.get("primary_email") or "").strip()
            if em and "email_not_unlocked" not in em.lower():
                p["email"] = em


def _zerobounce_ok(status: str) -> bool:
    s = (status or "").lower().strip()
    if s == "valid":
        return True
    if s in ("invalid", "catch-all", "spamtrap", "abuse", "do_not_mail", "unknown"):
        return False
    return False


def _zb_validate(client: httpx.Client, api_key: str, email: str) -> bool:
    r = client.get(
        ZEROBOUNCE_VALIDATE,
        params={"api_key": api_key, "email": email, "ip_address": ""},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    st = data.get("status") or data.get("Status") or ""
    return _zerobounce_ok(str(st))


def _prospect_domain_exists(supabase_url: str, domain: str) -> bool:
    if not domain:
        return True
    r = httpx.get(
        f"{supabase_url}/rest/v1/prospects",
        headers=_sb_headers(),
        params={"domain": f"eq.{domain}", "select": "id", "limit": "1"},
        timeout=15.0,
    )
    r.raise_for_status()
    return bool(r.json())


def _suppression_hit(supabase_url: str, email: str, domain: str) -> bool:
    r1 = httpx.get(
        f"{supabase_url}/rest/v1/suppressions",
        headers=_sb_headers(),
        params={"email": f"eq.{email}", "select": "id", "limit": "1"},
        timeout=15.0,
    )
    if r1.status_code == 200 and r1.json():
        return True
    r2 = httpx.get(
        f"{supabase_url}/rest/v1/suppressions",
        headers=_sb_headers(),
        params={"domain": f"eq.{domain}", "select": "id", "limit": "1"},
        timeout=15.0,
    )
    return r2.status_code == 200 and bool(r2.json())


# Maps a vertical's label (see INDUSTRY_DAYS) to the applicable US regulatory
# anchor Charlotte should cite in the email body. Keep wording short and
# recognizable to practice owners — the LLM pulls straight from this string.
INDUSTRY_REGULATION: dict[str, str] = {
    "Dental Clinics": "HIPAA (45 CFR 164)",
    "Medical Clinics": "HIPAA (45 CFR 164)",
    "Physiotherapy": "HIPAA (45 CFR 164)",
    "Optometry": "HIPAA (45 CFR 164)",
    "Law Firms": "ABA Formal Opinion 2024-3 (cyber ethics)",
    "Accounting Firms": "FTC Safeguards Rule (16 CFR 314)",
    "Financial Advisors": "FTC Safeguards Rule (16 CFR 314)",
}


def _regulation_for(industry: str) -> str:
    """Return the US regulatory anchor for a given industry/vertical label."""
    key = (industry or "").strip()
    if key in INDUSTRY_REGULATION:
        return INDUSTRY_REGULATION[key]
    lowered = key.lower()
    if any(w in lowered for w in ("dental", "medical", "clinic", "physio", "optomet", "health")):
        return "HIPAA (45 CFR 164)"
    if any(w in lowered for w in ("law", "legal", "attorney", "lawyer")):
        return "ABA Formal Opinion 2024-3 (cyber ethics)"
    if any(w in lowered for w in ("accoun", "cpa", "bookkeep", "tax", "financial", "wealth")):
        return "FTC Safeguards Rule (16 CFR 314)"
    return ""


def _claude_prompt(
    *,
    first_name: str,
    company: str,
    industry: str,
    city: str,
    domain: str,
    score: int,
    grade: str,
    top_finding: str,
    top_severity: str,
    breach_detected: bool,
    breach_detail: str,
) -> str:
    regulation = _regulation_for(industry)
    reg_line = f"- Applicable regulation: {regulation}" if regulation else "- Applicable regulation: (none — skip regulatory framing)"
    reg_rule = (
        f"17. Frame the finding against {regulation}. Reference the regulation by name at least once in the body."
        if regulation
        else "17. Do not invent a regulation. If no regulation applies, skip regulatory framing entirely."
    )
    return f"""You are Charlotte, an outbound email writer for HAWK Security.
You write short, high-converting cold emails for US small businesses.

Prospect details:
- Name: {first_name}
- Company: {company}
- Industry: {industry}
- City: {city}
- Domain: {domain}
- HAWK Score: {score}/100
- Grade: {grade}
- Top finding: {top_finding}
- Finding severity: {top_severity}
- Breach detected: {str(breach_detected).lower()}
- Breach detail: {breach_detail}
{reg_line}

Rules:
1. Open with the most alarming finding. Never open with "I hope this finds you well" or "My name is"
2. Use their actual domain name in the first sentence
3. Explain the finding in plain English for their specific business type
4. Include their score and grade
5. End with one low-friction ask: offer to send the full report
6. Under 100 words for the body
7. Subject line must mention their domain or a specific finding
8. Subject line must be lowercase
9. Never use: leverage, synergy, touch base, circle back, reach out, game-changer
10. Sound like a real person who actually ran a scan
11. If breach_detected is true, lead with the breach
12. If severity is Critical, use words like urgent, immediately, right now
13. Vary your opening line every time
14. Never use dashes or hyphens anywhere. Use commas or periods instead
15. No bullet points or numbered lists in the body
16. Short punchy sentences. No sentence over 20 words.
{reg_rule}

Return ONLY this JSON:
{{
  "subject": "subject line here",
  "body": "email body here"
}}
"""


async def _scan_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    domain: str,
    industry: str | None,
) -> dict[str, Any] | None:
    from services.scan_cache import get_cached_scan, set_cached_scan

    async with sem:
        cached = get_cached_scan(domain, "fast")
        if cached and cached.get("score") is not None:
            return cached
        try:
            r = await client.post(
                f"{SCANNER_URL}/v1/scan/sync",
                json={
                    "domain": domain.strip(),
                    "industry": industry or None,
                    "scan_depth": "fast",
                },
                timeout=SCAN_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("message") == "scan_timeout":
                return data
            if isinstance(data, dict) and data.get("score") is None:
                return data
            if isinstance(data, dict) and data.get("score") is not None:
                set_cached_scan(domain, "fast", data)
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("scan failed domain=%s err=%s", domain, e)
            return None


async def _openai_email_one(
    openai_key: str, row: dict[str, Any], scan: dict[str, Any], vertical_label: str
) -> dict[str, str] | None:
    findings_raw = scan.get("findings") or []
    findings = [dict(f) for f in findings_raw if isinstance(f, dict)]
    findings.sort(key=lambda x: _rank_sev(str(x.get("severity", ""))))
    top = findings[0] if findings else {}
    top_plain = _finding_plain(top) if top else "No major issues flagged."
    top_sev = str(top.get("severity") or "unknown") if top else "unknown"
    breach_detected, breach_detail = _breach_info(findings)
    if breach_detected and findings:
        for f in findings[:5]:
            layer = str(f.get("layer") or "").lower()
            if any(x in layer for x in ("breach", "hibp", "stealer")):
                top_plain = _finding_plain(f)
                top_sev = str(f.get("severity") or top_sev)
                break
    score = int(scan.get("score") or 0)
    grade = str(scan.get("grade") or "")
    prompt = _claude_prompt(
        first_name=row.get("first_name") or "there",
        company=row.get("company") or row.get("domain", "your company"),
        industry=row.get("industry") or vertical_label,
        city=row.get("city") or "United States",
        domain=row["domain"],
        score=score,
        grade=grade,
        top_finding=top_plain,
        top_severity=top_sev,
        breach_detected=breach_detected,
        breach_detail=breach_detail or "none noted",
    )
    for attempt in range(2):
        try:
            text = await chat_text_async(
                api_key=openai_key,
                system=None,
                user_messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                model=CHARLOTTE_OPENAI_MODEL,
            )
            parsed = _parse_claude_json(text)
            if parsed:
                parsed["subject"] = _sanitize_no_hyphens(parsed["subject"])
                parsed["body"] = _sanitize_no_hyphens(parsed["body"])
                return parsed
            if attempt == 0:
                continue
        except Exception as e:
            if attempt == 0:
                continue
            logger.warning("OpenAI email generation failed: %s", e)
            return None
    return None


def _smartlead_lead_payload(
    row: dict[str, Any],
    scan: dict[str, Any],
    email_body: dict[str, str],
    sender_name: str,
) -> dict[str, Any]:
    findings_raw = scan.get("findings") or []
    findings = [dict(f) for f in findings_raw if isinstance(f, dict)]
    findings.sort(key=lambda x: _rank_sev(str(x.get("severity", ""))))
    top_plain = _finding_plain(findings[0]) if findings else ""
    score = int(scan.get("score") or 0)
    grade = str(scan.get("grade") or "")
    fn = row.get("first_name") or "there"
    ind = row.get("industry") or ""
    dom = row["domain"]
    seq = _sequence_bodies(sender_name, fn, dom, ind, score)
    return {
        "first_name": row.get("first_name") or "",
        "last_name": row.get("last_name") or "",
        "email": row["email"],
        "company_name": row.get("company") or "",
        "website": dom,
        "custom_fields": {
            "hawk_score": str(score),
            "hawk_grade": grade,
            "top_finding": top_plain[:2000],
            "industry": ind[:500],
        },
        "email_1_subject": email_body["subject"],
        "email_1_body": email_body["body"],
        "email_2_subject": seq["email_2_subject"],
        "email_2_body": seq["email_2_body"],
        "email_3_subject": seq["email_3_subject"],
        "email_3_body": seq["email_3_body"],
        "email_4_subject": seq["email_4_subject"],
        "email_4_body": seq["email_4_body"],
    }


def _sequence_bodies(
    sender_name: str, first_name: str, domain: str, industry: str, score: int
) -> dict[str, str]:
    ind = industry or "your sector"
    return {
        "email_2_subject": _sanitize_no_hyphens(f"re: {domain} security scan"),
        "email_2_body": (
            f"Hi {first_name},\n\n"
            f"Wanted to follow up on the scan I ran on {domain}.\n\n"
            f"We recently helped a {ind} in the US with a similar score avoid what their insurer estimated would have been a six-figure breach.\n\n"
            f"Still happy to send you the full report if useful.\n\n"
            f"{sender_name}\n"
            "HAWK Security"
        ),
        "email_3_subject": _sanitize_no_hyphens(f"{ind} security scores this week"),
        "email_3_body": (
            f"Hi {first_name},\n\n"
            f"I have been scanning {ind} businesses across the US this week. The average score in your sector is 68/100. {domain} scored {score}/100.\n\n"
            "Attackers target the weakest businesses first. That gap matters.\n\n"
            "Full report is ready if you want it.\n\n"
            f"{sender_name}\n"
            "HAWK Security"
        ),
        "email_4_subject": _sanitize_no_hyphens("closing your file"),
        "email_4_body": (
            f"Hi {first_name},\n\n"
            f"Going to close out your security report for {domain} since I have not heard back.\n\n"
            "If things change and you want to see what we found, just reply and I will send it over.\n\n"
            f"{sender_name}\n"
            "HAWK Security"
        ),
    }


async def _process_pipeline_async(
    leads: list[dict[str, Any]],
    vertical_label: str,
    openai_key: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Scan up to SCAN_CONCURRENCY in parallel; then OpenAI + validation per successful scan."""
    sem = asyncio.Semaphore(SCAN_CONCURRENCY)
    counts = {
        "domains_scanned": 0,
        "scan_failures": 0,
        "scan_skipped": 0,
        "email_failed": 0,
        "emails_written": 0,
    }
    out_rows: list[dict[str, Any]] = []

    async with httpx.AsyncClient() as hc:

        async def scan_row(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
            r = await _scan_one(hc, sem, row["domain"], row.get("industry") or vertical_label)
            return row, r

        scan_results = await asyncio.gather(*[scan_row(row) for row in leads])

        for row, scan in scan_results:
            if not scan:
                counts["scan_failures"] += 1
                continue
            if scan.get("message") == "scan_timeout" or scan.get("score") is None:
                counts["scan_skipped"] += 1
                continue
            counts["domains_scanned"] += 1
            ce = await _openai_email_one(openai_key, row, scan, vertical_label)
            if not ce:
                counts["email_failed"] += 1
                continue
            if not _validate_email_content(ce, row, scan):
                counts["email_failed"] += 1
                continue
            counts["emails_written"] += 1
            sender = os.environ.get("CHARLOTTE_SENDER_NAME", "Charlotte").strip()
            payload = _smartlead_lead_payload(row, scan, ce, sender)
            out_rows.append({"row": row, "scan": scan, "smartlead": payload, "email_body": ce})

    return out_rows, counts


def run_charlotte_daily() -> dict[str, Any]:
    dry = os.environ.get("CHARLOTTE_AUTOMATION_DRY_RUN", "").strip() in ("1", "true", "yes")
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    apollo_key = os.environ.get("APOLLO_API_KEY", "").strip()
    zb_key = os.environ.get("ZEROBOUNCE_API_KEY", "").strip()
    sl_key = os.environ.get("SMARTLEAD_API_KEY", "").strip()
    sl_cid = os.environ.get("SMARTLEAD_CAMPAIGN_ID", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    stats = {
        "ok": True,
        "dry_run": dry,
        "industry": None,
        "leads_pulled": 0,
        "emails_verified": 0,
        "emails_suppressed": 0,
        "domains_scanned": 0,
        "scan_failures": 0,
        "scan_skipped": 0,
        "email_failed": 0,
        "upload_failed": 0,
        "emails_written": 0,
        "leads_uploaded": 0,
    }
    run_row_id: str | None = None

    if not supabase_url:
        return {**stats, "ok": False, "error": "SUPABASE_URL not set"}

    day_s = _get_setting(supabase_url, "charlotte_industry_day_index", "0")
    try:
        day_idx = int(day_s) % len(INDUSTRY_DAYS)
    except ValueError:
        day_idx = 0
    industry_cfg = INDUSTRY_DAYS[day_idx]
    stats["industry"] = industry_cfg["label"]

    if dry:
        _ceo_sms_summary(stats)
        return stats

    if not apollo_key or not zb_key or not sl_key or not openai_key:
        return {
            **stats,
            "ok": False,
            "error": "Missing APOLLO_API_KEY, ZEROBOUNCE_API_KEY, SMARTLEAD_API_KEY, or OPENAI_API_KEY",
        }

    if not sl_cid:
        sl_cid = _get_setting(supabase_url, "smartlead_campaign_id", "").strip()
    if not sl_cid:
        return {**stats, "ok": False, "error": "SMARTLEAD_CAMPAIGN_ID or crm_settings smartlead_campaign_id required"}

    run_row_id = _begin_charlotte_run_row(supabase_url, industry_cfg["label"])

    # --- Apollo: 2 pages x 100
    pulled: list[dict[str, Any]] = []
    with httpx.Client(timeout=180.0) as client:
        for page in (1, 2):
            part = _apollo_search_page(client, industry_cfg, page=page, per_page=100)
            pulled.extend(part)
        _apollo_bulk_match_emails(client, pulled)

    stats["leads_pulled"] = len(pulled)

    # Dedupe by email
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for p in pulled:
        em = (p.get("email") or "").strip().lower()
        if not em or em in seen:
            continue
        seen.add(em)
        dom = _normalize_domain(p.get("website") or "")
        if not dom:
            continue
        p["domain"] = dom
        uniq.append(p)

    # ZeroBounce
    suppressed = 0
    verified: list[dict[str, Any]] = []
    with httpx.Client(timeout=60.0) as client:
        for p in uniq:
            try:
                if not _zb_validate(client, zb_key, p["email"]):
                    suppressed += 1
                    continue
            except Exception as e:
                logger.warning("zerobounce skip %s: %s", p.get("email"), e)
                suppressed += 1
                continue
            verified.append(p)

    stats["emails_verified"] = len(verified)

    # Supabase suppressions + existing prospects
    ready: list[dict[str, Any]] = []
    sup_count = 0
    for p in verified:
        d = p["domain"]
        em = p["email"]
        if _suppression_hit(supabase_url, em, d):
            sup_count += 1
            continue
        if _prospect_domain_exists(supabase_url, d):
            sup_count += 1
            continue
        ready.append(p)

    stats["emails_suppressed"] = sup_count

    # Scan + OpenAI (async)
    enriched, counts = asyncio.run(
        _process_pipeline_async(ready, industry_cfg["label"], openai_key)
    )
    stats["domains_scanned"] = counts["domains_scanned"]
    stats["scan_failures"] = counts["scan_failures"]
    stats["scan_skipped"] = counts["scan_skipped"]
    stats["email_failed"] = counts["email_failed"]
    stats["emails_written"] = counts["emails_written"]

    # Smartlead (retry once per batch; per-lead charlotte_emails on success)
    uploaded = 0
    upload_fail = 0
    if enriched:
        with httpx.Client(timeout=120.0) as client:
            for item in enriched:
                payload = item["smartlead"]
                chunk = [payload]
                ok_chunk = False
                lead_id = None
                for attempt in range(2):
                    try:
                        r = client.post(
                            f"{SMARTLEAD_BASE}/campaigns/{sl_cid}/leads",
                            params={"api_key": sl_key},
                            json={
                                "lead_list": chunk,
                                "settings": {
                                    "ignore_duplicate_leads_in_other_campaign": True,
                                    "return_lead_ids": True,
                                },
                            },
                            timeout=120.0,
                        )
                        if r.status_code >= 400:
                            logger.error("Smartlead error: %s %s", r.status_code, r.text[:800])
                            if attempt == 1:
                                upload_fail += 1
                            continue
                        data = r.json()
                        uploaded += int(data.get("added_count") or data.get("upload_count") or 1)
                        ok_chunk = True
                        lids = data.get("lead_ids") or data.get("ids") or []
                        if isinstance(lids, list) and lids:
                            lead_id = str(lids[0])
                        break
                    except Exception as e:
                        logger.warning("Smartlead post attempt %s: %s", attempt + 1, e)
                        if attempt == 1:
                            upload_fail += 1
                if ok_chunk:
                    _insert_charlotte_email_row(
                        supabase_url,
                        run_id=run_row_id,
                        row=item["row"],
                        scan=item["scan"],
                        email_body=item["email_body"],
                        smartlead_lead_id=lead_id,
                    )
                else:
                    _smartlead_upload_failed_ceo_alert(item["row"])

    stats["leads_uploaded"] = uploaded
    stats["upload_failed"] = upload_fail

    _finalize_charlotte_run(supabase_url, run_row_id, stats)
    _ceo_sms_summary(stats, supabase_url)

    next_idx = (day_idx + 1) % len(INDUSTRY_DAYS)
    _set_setting(supabase_url, "charlotte_industry_day_index", str(next_idx))

    return stats


def _smartlead_upload_failed_ceo_alert(row: dict[str, Any]) -> None:
    from services.crm_openphone import send_sms

    num = os.environ.get("CRM_CEO_PHONE_E164", "").strip() or "+18259458282"
    msg = (
        "Charlotte Smartlead upload failed after retry.\n"
        f"Domain: {row.get('domain')}\n"
        f"Email: {row.get('email')}\n"
        "Check logs and re-push lead manually."
    )
    try:
        send_sms(num, msg)
    except Exception:
        logger.exception("CEO SMS Smartlead failure alert")


def _ceo_sms_summary(stats: dict[str, Any], supabase_url: str = "") -> None:
    from services.crm_openphone import send_sms

    num = os.environ.get("CRM_CEO_PHONE_E164", "").strip() or "+18259458282"
    rate = 0.02
    if supabase_url:
        try:
            rate = float(_get_setting(supabase_url, "charlotte_estimated_reply_rate", "0.02"))
        except ValueError:
            rate = 0.02
    uploaded = int(stats.get("leads_uploaded", 0))
    est = int(round(uploaded * rate))
    msg = (
        "Charlotte daily run complete.\n"
        f"Industry: {stats.get('industry') or '—'}\n"
        f"Domains found: {stats.get('leads_pulled', 0)}\n"
        f"Emails verified: {stats.get('emails_verified', 0)}\n"
        f"Scans completed: {stats.get('domains_scanned', 0)}\n"
        f"Emails written: {stats.get('emails_written', 0)}\n"
        f"Uploaded to Smartlead: {uploaded}\n"
        f"Failures: {stats.get('scan_failures', 0) + stats.get('scan_skipped', 0) + stats.get('email_failed', 0) + stats.get('upload_failed', 0)}\n"
        f"Estimated replies today: {est}"
    )
    try:
        send_sms(num, msg)
    except Exception:
        logger.exception("CEO SMS Charlotte summary failed")
