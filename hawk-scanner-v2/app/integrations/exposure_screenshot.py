"""Playwright screenshots of login/admin surfaces (Phase 3)."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Skip huge payloads in DB/API responses
_MAX_DATA_URL_CHARS = 450_000

_LOGIN_PATH_HINTS: tuple[str, ...] = (
    "login",
    "signin",
    "sign-in",
    "signup",
    "admin",
    "wp-admin",
    "wp-login",
    "dashboard",
    "panel",
    "manage",
    "oauth",
    "/auth",
    "portal",
    "cpanel",
    "webmail",
    "secure",
    "account",
)


def candidate_login_urls(jsonl: list[dict[str, Any]], *, max_urls: int = 2) -> list[str]:
    out: list[str] = []
    for row in jsonl:
        u = row.get("url") or row.get("final_url") or ""
        if not u or not str(u).startswith("http"):
            continue
        base = str(u).split("?")[0].strip()
        low = base.lower()
        if any(h in low for h in _LOGIN_PATH_HINTS):
            out.append(base)
    dedup: list[str] = []
    for u in out:
        if u not in dedup:
            dedup.append(u)
        if len(dedup) >= max_urls:
            break
    return dedup


async def capture_exposure_screenshots(
    jsonl: list[dict[str, Any]],
    domain: str,
) -> list[dict[str, Any]]:
    """
    Capture 1–2 JPEG screenshots of likely login/admin URLs from httpx JSONL.
    Disabled when HAWK_SCREENSHOTS_DISABLED=1 or Playwright unavailable.
    """
    if os.environ.get("HAWK_SCREENSHOTS_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return []

    urls = candidate_login_urls(jsonl, max_urls=int(os.environ.get("HAWK_SCREENSHOT_MAX_URLS", "2")))
    if not urls:
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("playwright not installed — exposure screenshots skipped")
        return []

    out: list[dict[str, Any]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (compatible; HAWK-SecurityScanner/2.0; +https://securedbyhawk.com) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            for url in urls:
                try:
                    await page.goto(url, timeout=18_000, wait_until="domcontentloaded")
                    await asyncio.sleep(0.5)
                    png = await page.screenshot(type="jpeg", quality=58, full_page=False)
                except Exception as e:
                    logger.info("screenshot skip %s: %s", url, e)
                    continue
                b64 = base64.b64encode(png).decode("ascii")
                data_url = f"data:image/jpeg;base64,{b64}"
                if len(data_url) > _MAX_DATA_URL_CHARS:
                    data_url = data_url[:_MAX_DATA_URL_CHARS] + "...(truncated)"
                out.append(
                    {
                        "id": str(uuid.uuid4()),
                        "severity": "medium",
                        "category": "Exposure evidence",
                        "title": "Live view of a public login or admin surface",
                        "description": (
                            f"This is what a browser sees when visiting `{url}` right now. "
                            "If this should not be public, restrict access or move to VPN."
                        ),
                        "technical_detail": url[:2000],
                        "affected_asset": url,
                        "remediation": "Restrict admin/login to trusted IPs or VPN; enforce MFA; remove exposed panels from the internet.",
                        "layer": "exposure_screenshot",
                        "screenshot_data_url": data_url,
                    }
                )
            await browser.close()
    except Exception:
        logger.exception("exposure screenshot batch failed")
    return out
