"""HaveIBeenPwned API v3 service — check individual emails for data breaches."""
from __future__ import annotations

import time

import httpx

from backend.config import HIBP_API_KEY

HIBP_BASE_URL = "https://haveibeenpwned.com/api/v3"
HIBP_RATE_DELAY = 1.6  # seconds between requests (HIBP rate limit: ~1 req/1500ms)
USER_AGENT = "HAWK-CRM-BreachCheck/1.0"


def check_email(email: str) -> list[dict]:
    """
    Check a single email address against HIBP.

    Returns list of breach dicts (name, title, breach_date, data_classes, is_verified).
    Returns empty list if email not found in any breach.
    Raises httpx.HTTPStatusError on unexpected API errors.
    """
    url = f"{HIBP_BASE_URL}/breachedaccount/{email}"
    headers = {
        "hibp-api-key": HIBP_API_KEY,
        "user-agent": USER_AGENT,
    }
    params = {"truncateResponse": "false"}

    with httpx.Client(timeout=15) as client:
        r = client.get(url, headers=headers, params=params)

    if r.status_code == 404:
        return []

    r.raise_for_status()
    breaches = r.json()

    return [
        {
            "name": b.get("Name", ""),
            "title": b.get("Title", ""),
            "breach_date": b.get("BreachDate", ""),
            "data_classes": b.get("DataClasses", []),
            "is_verified": b.get("IsVerified", False),
            "pwn_count": b.get("PwnCount", 0),
        }
        for b in breaches
    ]


def check_domain_emails(emails: list[str]) -> list[dict]:
    """
    Check a list of emails against HIBP, respecting rate limits.

    Returns list of result dicts per email:
      { email, breached, breach_count, breaches: [...] }
    """
    results = []
    for i, email in enumerate(emails):
        if i > 0:
            time.sleep(HIBP_RATE_DELAY)

        try:
            breaches = check_email(email.strip().lower())
            results.append(
                {
                    "email": email.strip().lower(),
                    "breached": len(breaches) > 0,
                    "breach_count": len(breaches),
                    "breaches": breaches,
                }
            )
        except httpx.HTTPStatusError as exc:
            # 401 = bad API key, 429 = rate limited — surface as error entry
            results.append(
                {
                    "email": email.strip().lower(),
                    "breached": False,
                    "breach_count": 0,
                    "breaches": [],
                    "error": f"HIBP error {exc.response.status_code}",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "email": email.strip().lower(),
                    "breached": False,
                    "breach_count": 0,
                    "breaches": [],
                    "error": str(exc),
                }
            )

    return results
