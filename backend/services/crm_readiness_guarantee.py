"""P3 — Readiness score, guarantee status, SLA tracking, critical alerts (after Shield rescan)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import CRM_CEO_PHONE_E164, CRM_PUBLIC_BASE_URL
from services.crm_openphone import send_sms
from services.crm_portal_email import shield_guarantee_at_risk_email

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _portal_email_and_first_name(client_id: str, prospect_id: str | None) -> tuple[str | None, str]:
    """Client portal login email + first name for transactional email."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_headers(),
        params={"client_id": f"eq.{client_id}", "select": "email", "limit": "1"},
        timeout=20.0,
    )
    email = None
    if r.status_code == 200 and r.json():
        email = (r.json()[0].get("email") or "").strip() or None
    first = "there"
    if prospect_id:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_headers(),
            params={"id": f"eq.{prospect_id}", "select": "contact_name", "limit": "1"},
            timeout=20.0,
        )
        if pr.status_code == 200 and pr.json():
            raw = (pr.json()[0].get("contact_name") or "").strip()
            if raw:
                first = raw.split()[0]
    return email, first


def _critical_finding_plain(row: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    fk = str(row.get("finding_key") or "")
    for f in findings:
        if _finding_key(f) == fk:
            t = str(f.get("title") or "").strip()
            if t:
                return t[:500]
            for k in ("interpretation", "plain_english", "description"):
                v = f.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()[:500]
    return fk.replace("|", " · ")[:500] if fk else "Critical finding — see portal for details."


def _finding_key(f: dict[str, Any]) -> str:
    layer = str(f.get("layer") or "").lower()[:80]
    title = str(f.get("title") or "").lower()[:200]
    asset = str(f.get("affected_asset") or "").lower()[:200]
    return f"{layer}|{title}|{asset}"


def _soft_finding_key(f: dict[str, Any]) -> str:
    return "|".join(
        [
            str(f.get("layer") or "").lower()[:80],
            str(f.get("title") or "").lower()[:200],
            str(f.get("affected_asset") or "").lower()[:200],
        ]
    )


def _normalize_severity(raw: str | None) -> str:
    s = (raw or "low").lower()
    if s in ("critical", "high", "medium", "low"):
        return s
    if s in ("warning",):
        return "medium"
    if s in ("info", "ok"):
        return "low"
    return "low"


def _findings_list(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        inner = raw.get("findings")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _fetch_sla_rows(client_id: str) -> list[dict[str, Any]]:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/hawk_finding_sla",
        headers=_headers(),
        params={"client_id": f"eq.{client_id}", "select": "*", "limit": "2000"},
        timeout=60.0,
    )
    if r.status_code >= 400:
        return []
    return r.json() or []


def _patch_sla(row_id: str, body: dict[str, Any]) -> None:
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/hawk_finding_sla",
        headers=_headers(),
        params={"id": f"eq.{row_id}"},
        json=body,
        timeout=20.0,
    ).raise_for_status()


def _insert_sla(body: dict[str, Any]) -> None:
    httpx.post(
        f"{SUPABASE_URL}/rest/v1/hawk_finding_sla",
        headers=_headers(),
        json=body,
        timeout=20.0,
    ).raise_for_status()


def _sync_sla_from_scan(
    client_id: str,
    findings: list[dict[str, Any]],
    now: datetime,
) -> None:
    current_keys: dict[str, str] = {}
    for f in findings:
        k = _finding_key(f)
        current_keys[k] = _normalize_severity(str(f.get("severity")))

    existing = {r["finding_key"]: r for r in _fetch_sla_rows(client_id)}

    for key, sev in current_keys.items():
        row = existing.get(key)
        if not row:
            _insert_sla(
                {
                    "client_id": client_id,
                    "finding_key": key,
                    "severity": sev,
                    "first_seen_at": now.isoformat(),
                    "last_seen_at": now.isoformat(),
                }
            )
            continue
        if row.get("cleared_at"):
            _patch_sla(
                str(row["id"]),
                {
                    "cleared_at": None,
                    "severity": sev,
                    "first_seen_at": now.isoformat(),
                    "last_seen_at": now.isoformat(),
                    "alert_20h_sent_at": None,
                    "alert_24h_sent_at": None,
                },
            )
        else:
            _patch_sla(
                str(row["id"]),
                {"last_seen_at": now.isoformat(), "severity": sev},
            )

    for key, row in existing.items():
        if key in current_keys:
            continue
        if row.get("cleared_at"):
            continue
        _patch_sla(str(row["id"]), {"cleared_at": now.isoformat()})


def _apply_verified_from_scan(client_id: str, prospect_id: str | None, now: datetime) -> None:
    if not prospect_id or not SUPABASE_URL:
        return
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers=_headers(),
        params={
            "prospect_id": f"eq.{prospect_id}",
            "select": "findings",
            "order": "created_at.desc",
            "limit": "1",
        },
        timeout=30.0,
    )
    if r.status_code >= 400 or not r.json():
        return
    row = r.json()[0]
    fl = _findings_list(row.get("findings"))

    verified_keys = {_soft_finding_key(f) for f in fl if f.get("verified_at")}
    if not verified_keys:
        return

    for sla in _fetch_sla_rows(client_id):
        if sla.get("cleared_at"):
            continue
        fk = str(sla.get("finding_key") or "")
        parts = fk.split("|", 2)
        if len(parts) == 3:
            pseudo = {"layer": parts[0], "title": parts[1], "affected_asset": parts[2]}
            sk = _soft_finding_key(pseudo)
            if sk in verified_keys:
                _patch_sla(str(sla["id"]), {"cleared_at": now.isoformat()})


def _compute_readiness(open_rows: list[dict[str, Any]], now: datetime) -> int:
    score = 100
    for row in open_rows:
        if row.get("cleared_at"):
            continue
        fs = _parse_ts(row.get("first_seen_at"))
        if not fs:
            continue
        age = now - fs
        sev = (row.get("severity") or "low").lower()
        if sev == "critical" and age > timedelta(hours=24):
            score -= 25
        elif sev == "high" and age > timedelta(hours=48):
            score -= 15
        elif sev == "medium" and age > timedelta(days=30):
            score -= 8
        elif sev == "low" and age > timedelta(days=60):
            score -= 3
    return max(0, min(100, score))


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _status_from_score(score: int) -> str:
    if score >= 85:
        return "active"
    if score >= 70:
        return "at_risk"
    return "suspended"


def _checklist_from_sla(open_rows: list[dict[str, Any]], now: datetime, subscription_ok: bool) -> tuple[bool, bool, bool]:
    crit_ok = True
    high_ok = True
    for row in open_rows:
        if row.get("cleared_at"):
            continue
        fs = _parse_ts(row.get("first_seen_at"))
        if not fs:
            continue
        age = now - fs
        sev = (row.get("severity") or "").lower()
        if sev == "critical" and age > timedelta(hours=24):
            crit_ok = False
        if sev == "high" and age > timedelta(hours=48):
            high_ok = False
    return crit_ok, high_ok, subscription_ok


def _log_guarantee_event(
    client_id: str,
    old_status: str | None,
    new_status: str | None,
    score: int,
    detail: dict[str, Any],
) -> None:
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/hawk_guarantee_events",
            headers=_headers(),
            json={
                "client_id": client_id,
                "old_status": old_status,
                "new_status": new_status,
                "readiness_score": score,
                "detail": detail,
            },
            timeout=20.0,
        ).raise_for_status()
    except Exception:
        logger.exception("hawk_guarantee_events insert failed client=%s", client_id)


def _fetch_client_guarantee_fields(client_id: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={
            "id": f"eq.{client_id}",
            "select": "guarantee_status,hawk_readiness_score,status",
            "limit": "1",
        },
        timeout=20.0,
    )
    if r.status_code >= 400 or not r.json():
        return None
    return r.json()[0]


def process_shield_client_post_scan(
    *,
    client_id: str,
    domain: str,
    company_name: str,
    prospect_id: str | None,
    findings: list[dict[str, Any]],
    phone: str | None,
) -> dict[str, Any]:
    """
    After Shield daily scan: SLA rows, readiness score, guarantee status, events, critical 20h/24h alerts, reinstate WA.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False}

    now = datetime.now(timezone.utc)
    base = (CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com").rstrip("/")
    portal = f"{base}/portal"

    _sync_sla_from_scan(client_id, findings, now)
    _apply_verified_from_scan(client_id, prospect_id, now)

    open_rows = [r for r in _fetch_sla_rows(client_id) if not r.get("cleared_at")]
    score = _compute_readiness(open_rows, now)

    prev = _fetch_client_guarantee_fields(client_id)
    old_status = (prev or {}).get("guarantee_status") or "active"
    client_status = (prev or {}).get("status") or "active"
    subscription_ok = client_status == "active"

    crit_chk, high_chk, sub_chk = _checklist_from_sla(open_rows, now, subscription_ok)
    new_status = _status_from_score(score)
    # P3c — unresolved critical 24h+ forces at least at_risk (unless score already suspended)
    if new_status != "suspended":
        for row in open_rows:
            if (row.get("severity") or "").lower() != "critical":
                continue
            fs = _parse_ts(row.get("first_seen_at"))
            if fs and (now - fs) >= timedelta(hours=24):
                new_status = "at_risk"
                break

    patch: dict[str, Any] = {
        "hawk_readiness_score": score,
        "guarantee_status": new_status,
        "guarantee_checklist_critical_ok": crit_chk,
        "guarantee_checklist_high_ok": high_chk,
        "guarantee_checklist_subscription_ok": sub_chk,
    }

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={"id": f"eq.{client_id}"},
        json=patch,
        timeout=20.0,
    ).raise_for_status()

    if new_status != old_status:
        _log_guarantee_event(
            client_id,
            old_status,
            new_status,
            score,
            {"domain": domain, "reason": "readiness_threshold"},
        )
        if new_status == "active" and old_status in ("at_risk", "suspended") and phone:
            try:
                send_sms(
                    phone,
                    "Your HAWK guarantee is reinstated. Coverage is active. Well done.",
                )
            except Exception:
                logger.exception("reinstate sms failed client=%s", client_id)

    # P3c — critical finding age alerts (per open critical row)
    for row in open_rows:
        if (row.get("severity") or "").lower() != "critical":
            continue
        fs = _parse_ts(row.get("first_seen_at"))
        if not fs:
            continue
        age = now - fs
        rid = str(row["id"])

        if age >= timedelta(hours=20) and age < timedelta(hours=24) and not row.get("alert_20h_sent_at"):
            crit_text = _critical_finding_plain(row, findings)
            portal_email, fn = _portal_email_and_first_name(client_id, prospect_id)
            if portal_email:
                try:
                    shield_guarantee_at_risk_email(
                        to_email=portal_email,
                        first_name=fn,
                        domain=domain,
                        critical_finding=crit_text,
                        portal_url=portal,
                    )
                except Exception:
                    logger.exception("20h guarantee-at-risk email failed client=%s", client_id)
            if phone:
                try:
                    send_sms(
                        phone,
                        f"HAWK Alert — {company_name} — critical security issue must be fixed within 4 hours "
                        f"to maintain guarantee coverage. Login: {portal.replace('https://', '')}",
                    )
                except Exception:
                    logger.exception("20h alert sms failed")
            _patch_sla(rid, {"alert_20h_sent_at": now.isoformat()})

        if age >= timedelta(hours=24) and not row.get("alert_24h_sent_at"):
            if phone:
                try:
                    send_sms(
                        phone,
                        "Your breach response guarantee is now suspended due to an unresolved critical finding. "
                        "Fix it immediately to reinstate coverage.",
                    )
                except Exception:
                    logger.exception("24h client sms failed")
            try:
                send_sms(
                    CRM_CEO_PHONE_E164 or "+18259458282",
                    f"Guarantee at risk — {company_name} — critical finding unresolved 24h+. Portal: {portal}",
                )
            except Exception:
                logger.exception("24h ceo sms failed")
            _patch_sla(rid, {"alert_24h_sent_at": now.isoformat()})

    return {
        "ok": True,
        "readiness_score": score,
        "guarantee_status": new_status,
        "open_findings_tracked": len(open_rows),
    }
