#!/usr/bin/env python3
"""
Charlotte outbound enrichment: Apollo CSV → HAWK Scanner (sync) → OpenAI email → Smartlead-ready CSV.

Usage:
  export SCANNER_URL=https://intelligent-rejoicing-production.up.railway.app
  export OPENAI_API_KEY=sk-...
  export SUPABASE_URL=...
  export SUPABASE_SERVICE_ROLE_KEY=...

  python scripts/charlotte_enrichment.py \\
    --input apollo_export.csv \\
    --output smartlead_ready.csv \\
    --batch-size 50 \\
    --delay 2

Apollo input columns: First Name, Last Name, Email, Company, Website, Industry, City
Output: first_name, last_name, email, company_name, website, hawk_score, hawk_grade,
        top_finding, email_subject, email_body, plus Smartlead sequence emails 2–4 columns.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
# Repo root (hawk-scanner-v2/)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SEVERITY_ORDER = ("critical", "high", "medium", "warning", "low", "info", "ok")

FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "hotmail.com",
        "hotmail.ca",
        "outlook.com",
        "outlook.ca",
        "live.com",
        "yahoo.com",
        "yahoo.ca",
        "ymail.com",
        "icloud.com",
        "me.com",
        "msn.com",
        "protonmail.com",
        "proton.me",
    }
)

MAX_TOKENS = 500
SCAN_TIMEOUT = 90.0

# Apollo column aliases (case-insensitive match)
APOLLO_COLS = {
    "first": ("First Name", "first name", "first_name", "FirstName"),
    "last": ("Last Name", "last name", "last_name", "LastName"),
    "email": ("Email", "email"),
    "company": ("Company", "company", "company_name"),
    "website": ("Website", "website", "domain", "Domain"),
    "industry": ("Industry", "industry"),
    "city": ("City", "city"),
}


def _norm_header(h: str) -> str:
    return (h or "").strip()


def _pick(row: dict[str, str], key: str) -> str:
    aliases = APOLLO_COLS.get(key, ())
    # exact keys first
    lower_map = {_norm_header(k).lower(): v for k, v in row.items()}
    for a in aliases:
        if a in row:
            return (row.get(a) or "").strip()
    for a in aliases:
        v = lower_map.get(a.lower())
        if v is not None:
            return str(v).strip()
    return ""


def normalize_domain(raw: str) -> str:
    d = (raw or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix) :]
    d = d.split("/")[0].split("?")[0].strip()
    if not d:
        return ""
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
    interp = f.get("interpretation")
    if isinstance(interp, str) and interp.strip():
        return interp.strip()
    pe = f.get("plain_english")
    if isinstance(pe, str) and pe.strip():
        return pe.strip()
    desc = f.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    title = f.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return ""


def _top_findings_sorted(findings: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    return sorted(findings, key=lambda x: _rank_sev(str(x.get("severity", ""))))[:limit]


def _breach_info(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    breach_markers = ("breach", "hibp", "stealer", "credential", "pwned")
    for f in findings:
        layer = str(f.get("layer") or "").lower()
        title = str(f.get("title") or "").lower()
        cat = str(f.get("category") or "").lower()
        blob = f"{layer} {title} {cat}"
        if any(m in blob for m in breach_markers):
            detail = _finding_plain(f)
            return True, detail[:500] if detail else title[:200]
    return False, ""


def _sanitize_no_hyphens(text: str) -> str:
    """Rule 14: no hyphens in subject/body; use commas."""
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
    sub = data.get("subject")
    body = data.get("body")
    if not isinstance(sub, str) or not isinstance(body, str):
        return None
    return {"subject": sub.strip().lower(), "body": body.strip()}


async def _is_suppressed(
    client: Any, base: str, key: str, domain: str, email: str
) -> bool:
    if not base or not key:
        return False
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    url = f"{base.rstrip('/')}/rest/v1/suppressions"
    try:
        r1 = await client.get(
            url,
            headers=headers,
            params={"domain": f"eq.{domain}", "select": "id", "limit": "1"},
            timeout=15.0,
        )
        if r1.status_code < 400 and r1.json():
            return True
        r2 = await client.get(
            url,
            headers=headers,
            params={"email": f"eq.{email}", "select": "id", "limit": "1"},
            timeout=15.0,
        )
        if r2.status_code < 400 and r2.json():
            return True
    except Exception:
        return False
    return False


async def _scan_domain(client: Any, scanner_url: str, domain: str, industry: str | None) -> dict[str, Any]:
    url = f"{scanner_url.rstrip('/')}/v1/scan/sync"
    r = await client.post(
        url,
        json={"domain": domain.strip(), "industry": industry or None},
        timeout=SCAN_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


async def _charlotte_email(
    oa_client: Any,
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
) -> dict[str, str] | None:
    prompt = f"""You are Charlotte, an outbound email writer for HAWK Security.
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

Rules you must follow:
1. Open with the most alarming finding. Never open with "I hope this finds you well" or "My name is"
2. Use their actual domain name in the first sentence
3. Explain the finding in plain English relevant to their specific business type
4. Include their score and grade
5. End with one low-friction ask: offer to send the full report
6. Under 100 words for the body
7. Subject line must mention their domain or a specific finding
8. Subject line must be lowercase
9. Never use: leverage, synergy, touch base, circle back, reach out, game-changer
10. Sound like a real person who actually ran a scan, not a marketing email
11. If breach_detected is true, lead with the breach finding above all others
12. If top severity is Critical, use words like urgent, immediately, right now
13. Vary your opening line. Do not start every email with the same words
14. Never use dashes or hyphens anywhere in the subject line or body. Use commas or periods instead
15. Never use bullet points or numbered lists in the email body
16. Write in short punchy sentences. No sentence longer than 20 words.

Return ONLY this JSON with no other text:
{{
  "subject": "subject line here",
  "body": "email body here"
}}
"""
    model = (os.environ.get("CHARLOTTE_OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o").strip()
    completion = await oa_client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = (completion.choices[0].message.content or "").strip()
    parsed = _parse_claude_json(text)
    if parsed:
        parsed["subject"] = _sanitize_no_hyphens(parsed["subject"])
        parsed["body"] = _sanitize_no_hyphens(parsed["body"])
    return parsed


def _sequence_templates(
    *,
    sender_name: str,
    first_name: str,
    domain: str,
    industry: str,
    score: int,
) -> dict[str, str]:
    """Smartlead follow-ups (Day 3, 7, 14). Email 1 is the personalised OpenAI output."""
    ind = industry or "your sector"
    return {
        "seq2_subject": _sanitize_no_hyphens(f"re: {domain} security scan"),
        "seq2_body": (
            f"Hi {first_name},\n\n"
            f"Wanted to follow up on the scan I ran on {domain}.\n\n"
            f"We recently helped a {ind} in the US with a similar score avoid what their insurer estimated would have been a six-figure breach.\n\n"
            f"Still happy to send you the full report if useful.\n\n"
            f"{sender_name}\n"
            "HAWK Security"
        ),
        "seq3_subject": _sanitize_no_hyphens(f"{ind} security scores this week"),
        "seq3_body": (
            f"Hi {first_name},\n\n"
            f"I have been scanning {ind} businesses across the US this week. The average score in your sector is 68/100. {domain} scored {score}/100.\n\n"
            "Attackers target the weakest businesses first. That gap matters.\n\n"
            "Full report is ready if you want it.\n\n"
            f"{sender_name}\n"
            "HAWK Security"
        ),
        "seq4_subject": _sanitize_no_hyphens("closing your file"),
        "seq4_body": (
            f"Hi {first_name},\n\n"
            f"Going to close out your security report for {domain} since I have not heard back.\n\n"
            "If things change and you want to see what we found, just reply and I will send it over.\n\n"
            f"{sender_name}\n"
            "HAWK Security"
        ),
    }


async def _process_row(
    sem: asyncio.Semaphore,
    delay: float,
    httpx_client: Any,
    openai_client: Any,
    scanner_url: str,
    supabase_url: str,
    supabase_key: str,
    sender_name: str,
    row: dict[str, str],
    dry_run: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (output dict or None, skip reason or None)."""
    first = _pick(row, "first")
    last = _pick(row, "last")
    email = _pick(row, "email")
    company = _pick(row, "company")
    website = _pick(row, "website")
    industry = _pick(row, "industry")
    city = _pick(row, "city")

    domain = normalize_domain(website)
    if not domain:
        return None, "no_website"

    local = email.split("@")[-1].lower() if "@" in email else ""
    if local in FREE_EMAIL_DOMAINS:
        return None, "free_email"

    async with sem:
        if delay > 0:
            await asyncio.sleep(delay)

        if dry_run:
            seq = _sequence_templates(
                sender_name=sender_name,
                first_name=first or "there",
                domain=domain,
                industry=industry,
                score=0,
            )
            out = {
                "first_name": first,
                "last_name": last,
                "email": email,
                "company_name": company,
                "website": website,
                "hawk_score": "",
                "hawk_grade": "",
                "top_finding": "",
                "email_subject": "",
                "email_body": "",
                **seq,
            }
            return out, None

        if supabase_url and supabase_key:
            if await _is_suppressed(httpx_client, supabase_url, supabase_key, domain, email):
                return None, "suppressed"

        try:
            data = await _scan_domain(httpx_client, scanner_url, domain, industry or None)
        except Exception as e:
            return None, f"scan_error:{e!s}"

        findings_raw = data.get("findings") or []
        findings: list[dict[str, Any]] = [dict(f) for f in findings_raw if isinstance(f, dict)]
        top3 = _top_findings_sorted(findings, 3)
        top = top3[0] if top3 else {}
        top_plain = _finding_plain(top) if top else "No major issues flagged."
        top_sev = str(top.get("severity") or "unknown") if top else "unknown"

        breach_detected, breach_detail = _breach_info(findings)
        if breach_detected and top:
            # Prefer breach-heavy narrative for the LLM
            for f in top3:
                layer = str(f.get("layer") or "").lower()
                if "breach" in layer or "hibp" in layer or "stealer" in layer:
                    top_plain = _finding_plain(f)
                    top_sev = str(f.get("severity") or top_sev)
                    break

        score = int(data.get("score") or 0)
        grade = str(data.get("grade") or "")

        ce = None
        for attempt in range(2):
            try:
                ce = await _charlotte_email(
                    openai_client,
                    first_name=first or "there",
                    company=company or domain,
                    industry=industry or "business services",
                    city=city or "United States",
                    domain=domain,
                    score=score,
                    grade=grade,
                    top_finding=top_plain,
                    top_severity=top_sev,
                    breach_detected=breach_detected,
                    breach_detail=breach_detail or "none noted",
                )
            except Exception as e:
                if attempt == 0:
                    continue
                return None, f"openai_error:{e!s}"
            if ce:
                break
            if attempt == 0:
                continue
        if not ce:
            return None, "llm_parse"

        seq = _sequence_templates(
            sender_name=sender_name,
            first_name=first or "there",
            domain=domain,
            industry=industry,
            score=score,
        )
        out = {
            "first_name": first,
            "last_name": last,
            "email": email,
            "company_name": company,
            "website": website,
            "hawk_score": str(score),
            "hawk_grade": grade,
            "top_finding": top_plain,
            "email_subject": ce["subject"],
            "email_body": ce["body"],
            **seq,
        }
        return out, None


async def run(args: argparse.Namespace) -> int:
    from openai import AsyncOpenAI

    import httpx

    scanner_url = os.environ.get("SCANNER_URL", "http://127.0.0.1:8000").strip()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    sender_name = os.environ.get("CHARLOTTE_SENDER_NAME", "Charlotte").strip()

    if not args.dry_run and not api_key:
        print("OPENAI_API_KEY is required (or use --dry-run)", file=sys.stderr)
        return 1

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    out_fields = [
        "first_name",
        "last_name",
        "email",
        "company_name",
        "website",
        "hawk_score",
        "hawk_grade",
        "top_finding",
        "email_subject",
        "email_body",
        "seq2_subject",
        "seq2_body",
        "seq3_subject",
        "seq3_body",
        "seq4_subject",
        "seq4_body",
    ]

    stats: Counter[str] = Counter()
    results: list[tuple[int, dict[str, Any]]] = []

    sem = asyncio.Semaphore(max(1, args.batch_size))
    openai_client = None if args.dry_run else AsyncOpenAI(api_key=api_key)

    norm_rows = [{_norm_header(k): v for k, v in row.items()} for row in rows]

    async def run_one(
        hc: Any, idx: int, nr: dict[str, str]
    ) -> tuple[int, dict[str, Any] | None, str | None]:
        out, skip = await _process_row(
            sem,
            args.delay,
            hc,
            openai_client,
            scanner_url,
            supabase_url,
            supabase_key,
            sender_name,
            nr,
            args.dry_run,
        )
        return idx, out, skip

    async with httpx.AsyncClient() as hc:
        outcomes = await asyncio.gather(
            *[run_one(hc, i, nr) for i, nr in enumerate(norm_rows)],
            return_exceptions=True,
        )

    for item in outcomes:
        if isinstance(item, Exception):
            stats["skipped"] += 1
            stats["skip_exception"] += 1
            continue
        idx, out, skip = item
        if out:
            results.append((idx, out))
            stats["emails_written"] += 1
            stats["scanned_ok"] += 1
        else:
            stats["skipped"] += 1
            reason = (skip or "unknown").split(":")[0]
            stats[f"skip_{reason}"] += 1

    results.sort(key=lambda x: x[0])
    ordered = [r[1] for r in results]

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        for row in ordered:
            w.writerow({k: row.get(k, "") for k in out_fields})

    total = len(rows)
    scanned = stats["scanned_ok"]
    written = stats["emails_written"]
    skipped = stats["skipped"]

    print()
    print("=== Charlotte enrichment summary ===")
    print(f"Total rows in file:     {total}")
    print(f"Scanned successfully:   {scanned}")
    print(f"Emails written:         {written}")
    print(f"Total skipped:          {skipped}")
    for k, v in sorted(stats.items()):
        if k.startswith("skip_") and v:
            print(f"  - {k.replace('skip_', '')}: {v}")
    print(f"Output: {args.output}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Apollo → HAWK Scanner → OpenAI → Smartlead CSV")
    p.add_argument("--input", required=True, help="Apollo export CSV")
    p.add_argument("--output", required=True, help="Output CSV path")
    p.add_argument("--batch-size", type=int, default=1, help="Concurrent scans (semaphore)")
    p.add_argument("--delay", type=float, default=0.0, help="Seconds to sleep inside each slot (throttle)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse rows and write empty email fields (no Scanner/OpenAI)",
    )
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
