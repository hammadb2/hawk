"""HHS OCR public breach database scraper.

Source: https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf
Pulls every reported HIPAA breach affecting 500+ individuals (the public
"Wall of Shame") and upserts them into ``public.hhs_ocr_breach_incidents``.

Used by Charlotte cold-outreach to cite real, public, citable breaches in
the body of cold emails.

Run weekly via cron. Idempotent — uses a deterministic hash of
(name, state, date, type) as the row id so re-scrapes don't dup.

Driven by Playwright (the HHS portal is a JSF AJAX page; there's no plain
CSV/JSON endpoint). The CSV button is ``ocrForm:j_idt385`` in the rendered
HIPAA breach reports table.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PORTAL_URL = "https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# JSF auto-generates these column names ("javax.faces.component.UIPanel@…").
# Their position in the export is stable: 1st = entity name, 8th = business
# associate present.
JSF_NAME_COL_PREFIX = "javax.faces.component.UIPanel@"


def _row_id(row: dict[str, str]) -> str:
    key = "|".join([
        (row.get("covered_entity_name") or "").strip().lower(),
        (row.get("state") or "").strip().upper(),
        (row.get("breach_submission_date") or "").strip(),
        (row.get("breach_type") or "").strip().lower(),
        (row.get("breach_location") or "").strip().lower(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _normalize_csv(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    header = rows[0]
    # Repair JSF auto-generated column names by position.
    fixed_header = []
    for idx, h in enumerate(header):
        h_clean = h.strip()
        if h_clean.startswith(JSF_NAME_COL_PREFIX):
            if idx == 0:
                fixed_header.append("Name of Covered Entity")
            elif idx == 7:
                fixed_header.append("Business Associate Present")
            else:
                fixed_header.append(f"col_{idx}")
        else:
            fixed_header.append(h_clean)
    out: list[dict[str, Any]] = []
    for r in rows[1:]:
        if len(r) < len(fixed_header):
            r = r + [""] * (len(fixed_header) - len(r))
        rec_raw = dict(zip(fixed_header, r, strict=False))
        date_str = (rec_raw.get("Breach Submission Date") or "").strip()
        date_iso: str | None = None
        if date_str:
            for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
                try:
                    date_iso = datetime.strptime(date_str, fmt).date().isoformat()
                    break
                except ValueError:
                    continue
        try:
            individuals = int((rec_raw.get("Individuals Affected") or "0").replace(",", "").strip() or 0)
        except ValueError:
            individuals = 0
        ba_str = (rec_raw.get("Business Associate Present") or "").strip().lower()
        rec = {
            "covered_entity_name": (rec_raw.get("Name of Covered Entity") or "").strip(),
            "state": (rec_raw.get("State") or "").strip().upper() or None,
            "entity_type": (rec_raw.get("Covered Entity Type") or "").strip() or None,
            "individuals_affected": individuals,
            "breach_submission_date": date_iso,
            "breach_type": (rec_raw.get("Type of Breach") or "").strip() or None,
            "breach_location": (rec_raw.get("Location of Breached Information") or "").strip() or None,
            "business_associate_present": ba_str in ("yes", "true", "1"),
            "web_description": (rec_raw.get("Web Description") or "").strip() or None,
        }
        if not rec["covered_entity_name"]:
            continue
        rec["id"] = _row_id(rec)
        out.append(rec)
    return out


async def fetch_csv() -> bytes:
    """Drive the HHS portal in headless Chromium and download the CSV export."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright is required for HHS scraping; install via "
            "`pip install playwright && playwright install chromium`"
        ) from e
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(accept_downloads=True)
            page = await ctx.new_page()
            await page.goto(PORTAL_URL, wait_until="networkidle", timeout=60_000)
            await page.click("text=View HIPAA Breach Reports", timeout=15_000)
            await page.wait_for_load_state("networkidle", timeout=30_000)
            async with page.expect_download(timeout=120_000) as dl_info:
                await page.click("#ocrForm\\:j_idt385", timeout=15_000)
            dl = await dl_info.value
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tf:
                await dl.save_as(tf.name)
                return Path(tf.name).read_bytes()
        finally:
            await browser.close()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def _upsert_chunk(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    if not SUPABASE_URL or not SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    with httpx.Client(timeout=60) as c:
        r = c.post(
            f"{SUPABASE_URL}/rest/v1/hhs_ocr_breach_incidents?on_conflict=id",
            headers=_sb_headers(),
            json=rows,
        )
        if r.status_code >= 400:
            logger.error("hhs upsert failed status=%s body=%s", r.status_code, r.text[:500])
            r.raise_for_status()
    return len(rows)


async def run() -> dict[str, Any]:
    raw = await fetch_csv()
    rows = _normalize_csv(raw)
    # Dedupe by id — HHS occasionally has multiple rows per entity per
    # date/type combo (e.g. corrected filings). Keep the latest.
    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        by_id[r["id"]] = r
    deduped = list(by_id.values())
    written = 0
    chunk = 200
    for i in range(0, len(deduped), chunk):
        written += _upsert_chunk(deduped[i : i + chunk])
    return {
        "ok": True,
        "fetched": len(rows),
        "deduped": len(deduped),
        "written": written,
    }


def run_sync() -> dict[str, Any]:
    return asyncio.run(run())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_sync()
    logger.info("hhs scrape complete: %s", result)
    print(result)
