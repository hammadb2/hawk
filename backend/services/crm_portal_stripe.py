"""Stripe checkout.session.completed → provision client portal user + Shield Day 0 onboarding."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import (
    CAL_COM_BOOKING_URL,
    CRM_CEO_WHATSAPP_E164,
    CRM_PUBLIC_BASE_URL,
    STRIPE_PRICE_SHIELD,
    SUPABASE_URL,
)
from services.crm_portal_email import shield_day0_welcome_email, welcome_portal_email
from services.crm_twilio import send_whatsapp
from services.scanner import enqueue_async_scan

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

SEVERITY_ORDER = ("critical", "high", "medium", "warning", "low", "info", "ok")


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


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


def _findings_from_blob(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        inner = raw.get("findings")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _is_shield_client(client_row: dict[str, Any], session_obj: dict[str, Any]) -> bool:
    meta = session_obj.get("metadata") or {}
    if str(meta.get("hawk_product", "")).lower() == "shield":
        return True
    if str(meta.get("plan", "")).lower() in ("shield", "hawk_shield"):
        return True
    plan = (client_row.get("plan") or "").lower()
    if "shield" in plan:
        return True
    mrr = int(client_row.get("mrr_cents") or 0)
    if mrr >= 99700:
        return True
    # First-line subscription checkout amount (cents)
    try:
        amt = int(session_obj.get("amount_total") or 0)
        if amt >= 99700:
            return True
    except (TypeError, ValueError):
        pass
    # Expanded line_items in webhook (if present)
    lis = session_obj.get("line_items")
    if isinstance(lis, dict):
        for li in lis.get("data") or []:
            if not isinstance(li, dict):
                continue
            price = li.get("price") or {}
            pid = price.get("id") if isinstance(price, dict) else None
            if STRIPE_PRICE_SHIELD and pid == STRIPE_PRICE_SHIELD:
                return True
    return False


def _fetch_prospect(headers: dict[str, str], prospect_id: str | None) -> dict[str, Any] | None:
    if not prospect_id:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=headers,
        params={"id": f"eq.{prospect_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _top_finding_for_prospect(headers: dict[str, str], prospect_id: str | None) -> str:
    if not prospect_id:
        return "Pending first scan"
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers=headers,
        params={
            "prospect_id": f"eq.{prospect_id}",
            "select": "findings,hawk_score",
            "order": "created_at.desc",
            "limit": "1",
        },
        timeout=20.0,
    )
    if r.status_code >= 400:
        return "See portal for details"
    rows = r.json()
    if not rows:
        return "Pending first scan"
    findings = _findings_from_blob(rows[0].get("findings"))
    if not findings:
        return "Pending first scan"
    findings = sorted(findings, key=lambda x: _rank_sev(str(x.get("severity", ""))))
    plain = _finding_plain(findings[0])
    return (plain or "See portal for details")[:500]


def _find_client_row(headers: dict[str, str], session_obj: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve CRM client from Stripe session metadata or stripe_customer_id / email domain."""
    meta = session_obj.get("metadata") or {}
    cid = meta.get("crm_client_id") or meta.get("client_id")
    if cid:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=headers,
            params={"id": f"eq.{cid}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]

    cust = session_obj.get("customer")
    if isinstance(cust, dict):
        cust = cust.get("id")
    if cust:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=headers,
            params={"stripe_customer_id": f"eq.{cust}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]

    email = (session_obj.get("customer_email") or "").strip().lower()
    if not email and session_obj.get("customer_details"):
        email = (session_obj["customer_details"].get("email") or "").strip().lower()
    if email and "@" in email:
        domain = email.split("@", 1)[1].strip().lower()
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=headers,
            params={"domain": f"eq.{domain}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]

    return None


def _invite_portal_user(*, email: str, company_name: str, client_id: str) -> str | None:
    """Supabase Auth invite; returns new auth user id."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return None

    redir = f"{CRM_PUBLIC_BASE_URL}/portal" if CRM_PUBLIC_BASE_URL else None
    payload: dict[str, Any] = {
        "email": email.lower().strip(),
        "data": {
            "full_name": company_name,
            "portal_client_id": client_id,
        },
    }
    if redir:
        payload["options"] = {"email_redirect_to": redir}

    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/invite",
        headers=_sb_headers(),
        json=payload,
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("portal invite failed %s: %s — trying existing user lookup", r.status_code, r.text[:300])
        return _lookup_user_id_by_email(email)

    out = r.json()
    uid = out.get("id") if isinstance(out, dict) else None
    if uid:
        return str(uid)
    user = out.get("user") if isinstance(out, dict) else None
    if isinstance(user, dict) and user.get("id"):
        return str(user["id"])
    return None


def _lookup_user_id_by_email(email: str) -> str | None:
    """Find auth user id by email via GoTrue admin list (paginated scan)."""
    want = email.lower().strip()
    page = 1
    for _ in range(20):
        r = httpx.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=_sb_headers(),
            params={"page": str(page), "per_page": "100"},
            timeout=30.0,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        users = data.get("users") if isinstance(data, dict) else []
        for u in users or []:
            if (u.get("email") or "").lower() == want:
                uid = u.get("id")
                return str(uid) if uid else None
        if not users or len(users) < 100:
            break
        page += 1
    return None


def _seed_onboarding_sequence(headers: dict[str, str], client_id: str, now: datetime) -> None:
    steps = [
        ("welcome_email", now),
        ("scan_results_email", now + timedelta(minutes=2)),
        ("top_finding_24h", now + timedelta(hours=24)),
        ("portal_reminder_72h", now + timedelta(hours=72)),
        ("weekly_digest_7d", now + timedelta(days=7)),
    ]
    for step, when in steps:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_onboarding_sequences",
            headers=headers,
            json={
                "client_id": client_id,
                "step": step,
                "status": "pending",
                "metadata": {"scheduled_for": when.isoformat()},
            },
            timeout=20.0,
        )
        if r.status_code >= 400:
            logger.warning("sequence seed step %s failed: %s", step, r.text[:200])


def provision_portal_from_checkout(event: dict[str, Any]) -> bool:
    """
    On checkout.session.completed, link Stripe payment to a CRM client and invite portal user.
    Shield clients: Day 0 deep scan, WhatsApp (client + CEO), Resend welcome, onboarded_at + certification_eligible_at.
    Returns True if provisioning ran (even if partially skipped).
    """
    if event.get("type") != "checkout.session.completed":
        return False
    if not SUPABASE_URL or not SERVICE_KEY:
        return False

    session_obj = (event.get("data") or {}).get("object") or {}
    if not isinstance(session_obj, dict):
        return False

    headers = _sb_headers()
    client_row = _find_client_row(headers, session_obj)
    if not client_row:
        logger.info("portal provision: no matching CRM client for checkout session")
        return False

    shield = _is_shield_client(client_row, session_obj)

    if client_row.get("onboarded_at"):
        logger.info("portal provision: client %s already onboarded — idempotent skip", client_row.get("id"))
        return True

    # Non-Shield: duplicate checkout webhooks skip after first successful portal link
    if client_row.get("portal_user_id") and not shield:
        logger.info("portal provision: client %s already has portal (non-Shield) — skip", client_row.get("id"))
        return True

    email = (session_obj.get("customer_email") or "").strip().lower()
    if not email and session_obj.get("customer_details"):
        email = (session_obj["customer_details"].get("email") or "").strip().lower()
    if not email:
        logger.warning("portal provision: no customer email on session")
        return False

    cid = str(client_row["id"])
    prospect_id = client_row.get("prospect_id")
    prospect = _fetch_prospect(headers, str(prospect_id)) if prospect_id else None

    company = (client_row.get("company_name") or client_row.get("domain") or "there")[:200]
    domain = (client_row.get("domain") or "").strip()
    industry = (prospect.get("industry") if prospect else None) or "—"
    score = int((prospect.get("hawk_score") if prospect else None) or 0)
    top_finding = _top_finding_for_prospect(headers, str(prospect_id) if prospect_id else None)

    cust = session_obj.get("customer")
    if isinstance(cust, dict):
        cust = cust.get("id")
    cust = str(cust).strip() if cust else None

    # First deep scan (async) for Shield — full depth
    if shield and domain:
        try:
            enqueue_async_scan(
                domain,
                industry if industry != "—" else None,
                str(company) if company != "there" else None,
                scan_depth="full",
            )
        except Exception:
            logger.exception("Shield Day 0: enqueue deep scan failed for %s", domain)

    uid_existing = client_row.get("portal_user_id")
    uid = str(uid_existing).strip() if uid_existing else None
    if not uid:
        uid = _invite_portal_user(email=email, company_name=str(company), client_id=cid)
    if not uid:
        uid = _lookup_user_id_by_email(email)
    if not uid:
        logger.error("portal provision: could not create or resolve auth user for %s", email)
        return False

    now = datetime.now(timezone.utc)
    cert_at = now + timedelta(days=90)

    patch: dict[str, Any] = {
        "portal_user_id": uid,
        "onboarding_sequence_status": "in_progress",
    }
    if cust:
        patch["stripe_customer_id"] = cust
    if shield:
        patch["onboarded_at"] = now.isoformat()
        patch["certification_eligible_at"] = cert_at.isoformat()

    patch_req = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=headers,
        params={"id": f"eq.{cid}"},
        json=patch,
        timeout=20.0,
    )
    patch_req.raise_for_status()

    cpp_chk = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=headers,
        params={"client_id": f"eq.{cid}", "select": "id", "limit": "1"},
        timeout=20.0,
    )
    cpp_chk.raise_for_status()
    if not cpp_chk.json():
        cpp = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
            headers=headers,
            json={
                "user_id": uid,
                "client_id": cid,
                "email": email,
                "company_name": client_row.get("company_name"),
                "domain": client_row.get("domain"),
            },
            timeout=20.0,
        )
        if cpp.status_code >= 400:
            logger.error("client_portal_profiles insert failed: %s", cpp.text[:400])

    _seed_onboarding_sequence(headers, cid, now)

    base = CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com"
    portal_url = f"{base.rstrip('/')}/portal"
    portal_login = f"{base.rstrip('/')}/portal/login"

    if shield:
        try:
            shield_day0_welcome_email(
                to_email=email,
                company_name=str(company),
                portal_url=portal_login,
                booking_url=CAL_COM_BOOKING_URL,
            )
        except Exception:
            logger.exception("Shield Day 0 welcome email failed")

        wa_client = (
            "Welcome to HAWK Shield. Your breach response guarantee is now active. "
            "Your 90 day path to HAWK Certified starts today. "
            f"Book your onboarding call: {CAL_COM_BOOKING_URL} "
            f"Login: {portal_url.replace('https://', '')}"
        )
        phone = (prospect.get("phone") if prospect else None) or ""
        phone = str(phone).strip()
        if phone:
            try:
                send_whatsapp(phone, wa_client)
            except Exception:
                logger.exception("Shield Day 0: client WhatsApp failed")

        if CRM_CEO_WHATSAPP_E164:
            ceo_body = (
                "New Shield client. "
                f"Company: {company} Industry: {industry} "
                f"Score: {score}/100 Top finding: {top_finding} "
                "Guarantee: ACTIVE Day 1 of 90."
            )
            try:
                send_whatsapp(CRM_CEO_WHATSAPP_E164, ceo_body)
            except Exception:
                logger.exception("Shield Day 0: CEO WhatsApp failed")
    else:
        try:
            welcome_portal_email(to_email=email, company_name=str(company), portal_url=portal_login)
        except Exception:
            logger.exception("welcome email failed")

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/client_onboarding_sequences",
        headers=headers,
        params={"client_id": f"eq.{cid}", "step": "eq.welcome_email"},
        json={"status": "sent", "sent_at": now.isoformat()},
        timeout=20.0,
    )

    return True
