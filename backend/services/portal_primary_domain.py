"""Set clients.domain from the portal after generic-email signup (service role)."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from config import SUPABASE_URL
from services.portal_bootstrap import _headers, get_client_id_for_portal_user

logger = logging.getLogger(__name__)

# Reject using public mail hosts as the "company" apex we scan.
_PUBLIC_MAIL_APEX = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "gmx.com",
        "zoho.com",
        "yandex.com",
        "fastmail.com",
        "mail.com",
    }
)

_DOMAIN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$",
    re.IGNORECASE,
)


def normalize_primary_domain(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    low = s.lower()
    if "://" in low or low.startswith("//"):
        host = urlparse(low if "://" in low else f"https://{low}").hostname
        s = (host or "").strip()
    else:
        s = s.split("/")[0].split("?")[0].strip().lower()
    if s.startswith("www."):
        s = s[4:]
    return s


def set_portal_primary_domain(uid: str, raw_domain: str) -> dict[str, str]:
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    cid = get_client_id_for_portal_user(uid)
    if not cid:
        raise HTTPException(status_code=400, detail="No portal client linked to this account")

    domain = normalize_primary_domain(raw_domain)
    if not domain or len(domain) > 253:
        raise HTTPException(status_code=400, detail="Enter a valid company domain (e.g. example.com).")
    if domain in _PUBLIC_MAIL_APEX:
        raise HTTPException(
            status_code=400,
            detail="Use your company website domain to monitor (not a public email provider).",
        )
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail="Enter a valid domain name (letters, numbers, dots).")

    h = _headers()
    cp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=h,
        params={"id": f"eq.{cid}"},
        json={"domain": domain},
        timeout=20.0,
    )
    if cp.status_code >= 400:
        logger.error("portal primary domain clients patch: %s %s", cp.status_code, cp.text[:500])
        raise HTTPException(status_code=502, detail="Could not update client domain") from None

    cpp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=h,
        params={"user_id": f"eq.{uid}"},
        json={"domain": domain},
        timeout=20.0,
    )
    if cpp.status_code >= 400:
        logger.error("portal primary domain cpp patch: %s %s", cpp.status_code, cpp.text[:500])
        raise HTTPException(status_code=502, detail="Could not update portal profile domain") from None

    return {"ok": "true", "domain": domain}
