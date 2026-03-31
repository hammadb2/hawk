#!/usr/bin/env python3
"""
Charlotte enrichment: Apollo CSV → HAWK Scanner 2.0 per domain → top 3 findings →
Claude personalized outreach → enriched CSV for Smartlead.

Usage:
  export SCANNER_URL=https://your-railway-scanner.railway.app
  export ANTHROPIC_API_KEY=...
  python scripts/charlotte_enrichment.py --input apollo.csv --output smartlead.csv \\
    --domain-column domain --industry-column industry --contact-name-column name

Requires: httpx, anthropic (same as scanner service).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

# Allow running from repo root or hawk-scanner-v2/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


SEVERITY_ORDER = ("critical", "high", "medium", "low", "warning", "info", "ok")


def _rank_sev(s: str) -> int:
    s = (s or "low").lower()
    try:
        return SEVERITY_ORDER.index(s)
    except ValueError:
        return 99


async def scan_domain(client: "httpx.AsyncClient", base: str, domain: str, industry: str | None) -> dict:
    url = f"{base.rstrip('/')}/v1/scan/sync"
    r = await client.post(url, json={"domain": domain.strip(), "industry": industry or None}, timeout=600.0)
    r.raise_for_status()
    return r.json()


async def write_outreach(
    client: "anthropic.AsyncAnthropic",
    model: str,
    *,
    domain: str,
    company: str,
    contact: str,
    industry: str,
    top3: list[dict],
) -> str:
    payload = {
        "domain": domain,
        "company": company,
        "contact": contact,
        "industry": industry,
        "top_findings": top3,
    }
    prompt = (
        "Write a short, personalized cold email (under 180 words) to the contact. "
        "Reference their security posture using ONLY the findings given — be specific but not alarmist. "
        "Include one clear CTA to book a 15-minute posture review. No subject line. Plain text body only."
        f"\n\nCONTEXT:\n{json.dumps(payload, indent=2)}"
    )
    msg = await client.messages.create(
        model=model,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in msg.content:
        if block.type == "text":
            return block.text.strip()
    return ""


async def run(args: argparse.Namespace) -> None:
    import anthropic
    import httpx

    scanner_url = os.environ.get("SCANNER_URL", "http://127.0.0.1:8000")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY required for outreach generation", file=sys.stderr)
        sys.exit(1)

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    ac = anthropic.AsyncAnthropic(api_key=api_key)

    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    extra = [
        "hawk_score",
        "hawk_grade",
        "hawk_top_finding_1",
        "hawk_top_finding_2",
        "hawk_top_finding_3",
        "charlotte_outreach_body",
    ]
    out_fields = fieldnames + [c for c in extra if c not in fieldnames]

    async with httpx.AsyncClient() as hc:
        for row in rows:
            domain = (row.get(args.domain_column) or "").strip()
            industry = (row.get(args.industry_column) or "").strip() or None
            company = (row.get(args.company_column) or "").strip() if args.company_column else ""
            contact = (row.get(args.contact_name_column) or "").strip() if args.contact_name_column else ""
            if not domain:
                row["hawk_score"] = ""
                row["hawk_grade"] = ""
                for i in (1, 2, 3):
                    row[f"hawk_top_finding_{i}"] = ""
                row["charlotte_outreach_body"] = ""
                continue
            try:
                data = await scan_domain(hc, scanner_url, domain, industry)
            except Exception as e:
                row["hawk_score"] = f"error: {e}"
                row["hawk_grade"] = ""
                for i in (1, 2, 3):
                    row[f"hawk_top_finding_{i}"] = ""
                row["charlotte_outreach_body"] = ""
                continue

            findings = data.get("findings") or []
            findings_sorted = sorted(findings, key=lambda x: _rank_sev(str(x.get("severity", ""))))
            top3 = findings_sorted[:3]
            row["hawk_score"] = str(data.get("score", ""))
            row["hawk_grade"] = str(data.get("grade", ""))
            for i, f in enumerate(top3, start=1):
                row[f"hawk_top_finding_{i}"] = f.get("title", "")[:500]
            for j in range(len(top3) + 1, 4):
                row[f"hawk_top_finding_{j}"] = ""

            row["charlotte_outreach_body"] = await write_outreach(
                ac,
                model,
                domain=domain,
                company=company,
                contact=contact,
                industry=industry or "",
                top3=top3,
            )

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in out_fields})


def main() -> None:
    p = argparse.ArgumentParser(description="Apollo → scanner → Claude outreach CSV")
    p.add_argument("--input", required=True, help="Apollo export CSV path")
    p.add_argument("--output", required=True, help="Enriched CSV for Smartlead")
    p.add_argument("--domain-column", default="domain", help="Column with email domain")
    p.add_argument("--industry-column", default="industry", help="Industry for risk multiplier")
    p.add_argument("--company-column", default="company_name", help="Company name column (optional)")
    p.add_argument("--contact-name-column", default="name", help="Contact first name or full name")
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
