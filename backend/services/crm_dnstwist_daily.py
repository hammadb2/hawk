"""Daily dnstwist-only pass for Shield clients — diff registered permutations vs last snapshot, SMS on new."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import httpx

from config import CRM_PUBLIC_BASE_URL
from services.crm_openphone import send_sms
from services.scanner import run_dnstwist_scan

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _is_shield_plan(plan: str | None, mrr_cents: int | None) -> bool:
    p = (plan or "").strip().lower()
    if "starter" in p and "shield" not in p:
        return False
    if "shield" in p:
        return True
    mc = mrr_cents if mrr_cents is not None else 0
    return mc >= 99700


def _normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().replace("whatsapp:", "")
    if s.startswith("+"):
        digits = "+" + "".join(c for c in s[1:] if c.isdigit())
        return digits if len(digits) > 8 else None
    d = "".join(c for c in s if c.isdigit())
    return f"+{d}" if len(d) > 8 else None


def _registered_from_result(result: dict[str, Any]) -> list[str]:
    raw = (result.get("raw_layers") or {}).get("dnstwist") or {}
    reg = raw.get("registered") or []
    out: list[str] = []
    for item in reg:
        if isinstance(item, str):
            out.append(item.strip().lower())
        elif isinstance(item, dict):
            d = item.get("domain") or item.get("domain-name") or item.get("name")
            if d:
                out.append(str(d).strip().lower())
    return sorted(set(out))


def _fingerprint(names: list[str]) -> str:
    return hashlib.sha256(json.dumps(names).encode()).hexdigest()


def _latest_dnstwist_snapshot(client_id: str, domain: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_dnstwist_snapshots",
        headers=_headers(),
        params={
            "client_id": f"eq.{client_id}",
            "domain": f"eq.{domain}",
            "select": "id,registered_domains,fingerprint,created_at",
            "order": "created_at.desc",
            "limit": "1",
        },
        timeout=25.0,
    )
    if r.status_code >= 400:
        return None
    rows = r.json()
    return rows[0] if rows else None


def _insert_snapshot(client_id: str, domain: str, names: list[str], fp: str, raw: dict[str, Any]) -> None:
    body = {
        "client_id": client_id,
        "domain": domain,
        "registered_domains": names,
        "fingerprint": fp,
        "raw_json": raw,
    }
    ins = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_dnstwist_snapshots",
        headers=_headers(),
        json=body,
        timeout=25.0,
    )
    if ins.status_code >= 400:
        logger.error("client_dnstwist_snapshots insert failed: %s", ins.text[:400])


def run_daily_dnstwist_monitoring() -> dict[str, Any]:
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured", "processed": 0}

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={
            "status": f"eq.active",
            "select": "id,domain,company_name,plan,mrr_cents,prospect_id",
            "limit": "500",
        },
        timeout=60.0,
    )
    r.raise_for_status()
    clients = [c for c in (r.json() or []) if _is_shield_plan(c.get("plan"), c.get("mrr_cents"))]

    base = (CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com").rstrip("/")
    processed = 0
    alerts = 0
    errors: list[str] = []

    for c in clients:
        cid = str(c["id"])
        domain = (c.get("domain") or "").strip().lower()
        if not domain:
            continue
        company = (c.get("company_name") or domain).strip()
        pid = c.get("prospect_id")

        phone = None
        if pid:
            pr = httpx.get(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_headers(),
                params={"id": f"eq.{pid}", "select": "phone", "limit": "1"},
                timeout=15.0,
            )
            if pr.status_code == 200 and pr.json():
                phone = _normalize_phone((pr.json()[0] or {}).get("phone"))

        prev = _latest_dnstwist_snapshot(cid, domain)
        prev_set = set(prev.get("registered_domains") or []) if prev else set()

        try:
            result = run_dnstwist_scan(domain)
        except Exception as e:
            logger.exception("dnstwist scan failed %s", domain)
            errors.append(f"{domain}: {e}")
            continue

        names = _registered_from_result(result)
        fp = _fingerprint(names)
        raw_layers = result.get("raw_layers") or {}
        _insert_snapshot(cid, domain, names, fp, {"dnstwist": raw_layers.get("dnstwist"), "score": result.get("score")})

        new_only = sorted(set(names) - prev_set)
        processed += 1

        if not prev:
            continue

        if new_only and phone:
            try:
                body = (
                    f"HAWK — Daily lookalike check\n"
                    f"{company}\n"
                    f"New registered domain(s) similar to {domain}:\n"
                    f"{', '.join(new_only[:5])}\n"
                    f"Details: {base}/portal/findings"
                )
                out = send_sms(phone, body)
                if not out.get("skipped"):
                    alerts += 1
            except Exception:
                logger.exception("dnstwist whatsapp failed client=%s", cid)

    return {
        "ok": True,
        "shield_clients": len(clients),
        "processed": processed,
        "alerts_whatsapp": alerts,
        "errors": errors[:25],
    }
