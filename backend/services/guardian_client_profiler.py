"""Build or refresh `client_guardian_profiles` for a CRM client (Safe Browsing, WHOIS, BEC heuristics, lookalikes, OpenAI)."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from config import SUPABASE_URL
from services.openai_chat import chat_text_sync

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
GOOGLE_SAFE_BROWSING_API_KEY = os.environ.get("GOOGLE_SAFE_BROWSING_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _normalize_domain(raw: str | None) -> str:
    if not raw:
        return ""
    s = raw.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = s.split("/")[0].split(":")[0]
    return s


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _safe_browsing_check(url: str) -> str:
    if not GOOGLE_SAFE_BROWSING_API_KEY or not url:
        return "unknown"
    endpoint = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={GOOGLE_SAFE_BROWSING_API_KEY}"
    body = {
        "client": {"clientId": "hawk-guardian", "clientVersion": "1.0.0"},
        "threatInfo": {
            "threatTypes": [
                "MALWARE",
                "SOCIAL_ENGINEERING",
                "UNWANTED_SOFTWARE",
                "POTENTIALLY_HARMFUL_APPLICATION",
            ],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url[:2048]}],
        },
    }
    try:
        r = httpx.post(endpoint, json=body, timeout=15.0)
        if r.status_code >= 400:
            logger.warning("Safe Browsing HTTP %s: %s", r.status_code, r.text[:200])
            return "error"
        data = r.json()
        if data.get("matches"):
            return "threat"
        return "clean"
    except Exception:
        logger.exception("Safe Browsing request failed")
        return "error"


def _whois_creation_date(domain: str) -> datetime | None:
    if not domain:
        return None
    try:
        import whois  # type: ignore[import-untyped]

        w = whois.whois(domain)
        cd = getattr(w, "creation_date", None)
        if cd is None:
            return None
        if isinstance(cd, list):
            cd = cd[0]
        if isinstance(cd, datetime):
            if cd.tzinfo is None:
                return cd.replace(tzinfo=timezone.utc)
            return cd.astimezone(timezone.utc)
        if isinstance(cd, str):
            try:
                d = datetime.fromisoformat(cd.replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return d
            except Exception:
                return None
    except Exception:
        logger.debug("whois lookup failed for %s", domain, exc_info=True)
    return None


def _bec_score(*, company: str, domain: str, email: str) -> int:
    text = f"{company} {domain} {email}".lower()
    score = 0
    triggers = (
        "wire transfer",
        "gift card",
        "urgent payment",
        "invoice attached",
        "ceo request",
        "payroll",
        "w-2",
        "cryptocurrency",
        "bitcoin",
        "paypal security",
        "account suspended",
    )
    for t in triggers:
        if t in text:
            score += 18
    if re.search(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", text):
        score += 5
    return min(100, score)


def _lookalike_flags(domain: str, trusted: list[str]) -> list[dict[str, Any]]:
    d = _normalize_domain(domain)
    if not d:
        return []
    apex = d.lstrip("www.")
    flags: list[dict[str, Any]] = []
    for t in trusted:
        t = _normalize_domain(t)
        if not t or t == apex:
            continue
        dist = _levenshtein(apex, t)
        if 1 <= dist <= 2 and len(apex) >= 4:
            flags.append({"trusted": t, "candidate": apex, "distance": dist, "note": "possible homoglyph/typo domain"})
    return flags[:20]


def _default_login_urls(domain: str) -> list[str]:
    d = _normalize_domain(domain)
    if not d:
        return []
    base = d if d.startswith("www.") else f"www.{d}"
    return [
        f"https://{d}/login",
        f"https://{d}/signin",
        f"https://app.{d}/login",
        f"https://{base}/login",
    ]


def build_client_guardian_profile(client_id: str) -> dict[str, Any]:
    """
    Fetch client + prospect, run checks, upsert `client_guardian_profiles`.
    Returns the profile row payload (or partial on hard failure).
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}

    cid = str(client_id).strip()
    if not cid:
        return {"ok": False, "error": "missing client_id"}

    h = _headers()
    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=h,
        params={"id": f"eq.{cid}", "select": "id,domain,company_name,prospect_id", "limit": "1"},
        timeout=20.0,
    )
    cr.raise_for_status()
    crows = cr.json() or []
    if not crows:
        return {"ok": False, "error": "client not found"}
    client = crows[0]
    domain = _normalize_domain(client.get("domain"))
    company = (client.get("company_name") or domain or "Client")[:200]
    email = ""
    pid = client.get("prospect_id")
    if pid:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=h,
            params={"id": f"eq.{pid}", "select": "contact_email", "limit": "1"},
            timeout=15.0,
        )
        if pr.status_code < 400 and pr.json():
            email = (pr.json()[0].get("contact_email") or "").strip().lower()

    trusted_raw = os.environ.get("GUARDIAN_TRUSTED_DOMAINS", "securedbyhawk.com,hawk.ai").strip()
    trusted = [x.strip().lower() for x in trusted_raw.split(",") if x.strip()]
    if domain:
        trusted = list({*trusted, domain})

    check_url = f"https://{domain}/" if domain else ""
    sb = _safe_browsing_check(check_url) if check_url else "unknown"

    whois_dt = _whois_creation_date(domain) if domain else None
    bec = _bec_score(company=company, domain=domain, email=email)
    lookalikes = _lookalike_flags(domain, trusted)

    openai_warnings: list[dict[str, Any]] = []
    if OPENAI_API_KEY and domain:
        try:
            raw = chat_text_sync(
                api_key=OPENAI_API_KEY,
                system=(
                    "You output ONLY compact JSON: {\"warnings\":[{\"code\":\"\",\"severity\":\"low|medium|high\","
                    "\"message\":\"\"}]}. Max 6 warnings. Focus on phishing/BEC risks for this business domain."
                ),
                user_messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"company": company, "domain": domain, "contact_email": email},
                            ensure_ascii=False,
                        ),
                    }
                ],
                max_tokens=400,
            )
            parsed = json.loads(raw)
            for w in parsed.get("warnings") or []:
                if isinstance(w, dict) and w.get("message"):
                    openai_warnings.append(
                        {
                            "code": str(w.get("code") or "openai"),
                            "severity": str(w.get("severity") or "low"),
                            "message": str(w.get("message"))[:500],
                        }
                    )
        except Exception:
            logger.debug("OpenAI guardian warnings failed for client=%s", cid, exc_info=True)

    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "client_id": cid,
        "domain": domain or None,
        "known_login_urls": _default_login_urls(domain),
        "trusted_sender_domains": trusted[:50],
        "safe_browsing_status": sb,
        "domain_whois_created_at": whois_dt.isoformat() if whois_dt else None,
        "bec_risk_score": bec,
        "lookalike_flags": lookalikes,
        "openai_warnings": openai_warnings,
        "last_profiled_at": now,
        "updated_at": now,
    }

    exists = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_guardian_profiles",
        headers=h,
        params={"client_id": f"eq.{cid}", "select": "client_id", "limit": "1"},
        timeout=15.0,
    )
    if exists.status_code < 400 and (exists.json() or []):
        patch = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/client_guardian_profiles",
            headers=h,
            params={"client_id": f"eq.{cid}"},
            json={k: v for k, v in payload.items() if k != "client_id"},
            timeout=20.0,
        )
        if patch.status_code >= 400:
            logger.warning("guardian profile patch failed: %s %s", patch.status_code, patch.text[:300])
            return {"ok": False, "error": patch.text[:300], "partial": payload}
    else:
        ins = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_guardian_profiles",
            headers={**h, "Prefer": "return=minimal"},
            json=payload,
            timeout=20.0,
        )
        if ins.status_code >= 400:
            logger.warning("guardian profile insert failed: %s %s", ins.status_code, ins.text[:300])
            return {"ok": False, "error": ins.text[:300], "partial": payload}
    return {"ok": True, "profile": payload}


def schedule_build_client_guardian_profile(client_id: str) -> None:
    """Non-blocking fire-and-forget profiler (webhooks / bootstrap)."""

    def _run() -> None:
        try:
            build_client_guardian_profile(client_id)
        except Exception:
            logger.exception("background guardian profile failed client_id=%s", client_id)

    import threading

    threading.Thread(target=_run, name=f"guardian-profile-{client_id[:8]}", daemon=True).start()
