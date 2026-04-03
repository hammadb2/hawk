"""Shield onboarding Day 1 / 3 / 7 — triggered by POST /api/crm/cron/onboarding-sequences."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import CAL_COM_BOOKING_URL, CRM_PUBLIC_BASE_URL
from services.crm_portal_email import shield_day1_findings_email, shield_day7_week_summary_email
from services.crm_openphone import send_sms

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

SEVERITY_ORDER = ("critical", "high", "medium", "warning", "low", "info", "ok")


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


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


def _finding_title(f: dict[str, Any]) -> str:
    t = f.get("title")
    if isinstance(t, str) and t.strip():
        return t.strip()[:200]
    return _finding_plain(f)[:120] or "Finding"


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


def _portal_and_prospect(
    client_id: str, prospect_id: str | None
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    cpp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_headers(),
        params={"client_id": f"eq.{client_id}", "select": "email", "limit": "1"},
        timeout=20.0,
    )
    cpp.raise_for_status()
    cprows = cpp.json()
    email = (cprows[0].get("email") if cprows else None) or None

    prospect: dict[str, Any] | None = None
    if prospect_id:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_headers(),
            params={"id": f"eq.{prospect_id}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        if pr.status_code == 200 and pr.json():
            prospect = pr.json()[0]

    phone = (prospect or {}).get("phone")
    phone = str(phone).strip() if phone else None
    return email, prospect, phone


def _first_name(prospect: dict[str, Any] | None) -> str:
    if not prospect:
        return "there"
    raw = (prospect.get("contact_name") or "").strip()
    if not raw:
        return "there"
    return raw.split()[0]


def _latest_prospect_scan(prospect_id: str | None) -> tuple[list[dict[str, Any]], int | None]:
    if not prospect_id:
        return [], None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers=_headers(),
        params={
            "prospect_id": f"eq.{prospect_id}",
            "select": "findings,hawk_score",
            "order": "created_at.desc",
            "limit": "1",
        },
        timeout=20.0,
    )
    if r.status_code >= 400 or not r.json():
        return [], None
    row = r.json()[0]
    findings = _findings_list(row.get("findings"))
    findings = sorted(findings, key=lambda x: _rank_sev(str(x.get("severity", ""))))
    hs = row.get("hawk_score")
    score = int(hs) if isinstance(hs, int) else None
    return findings, score


def _top_findings_plain(findings: list[dict[str, Any]], n: int = 3) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for f in findings[:n]:
        out.append((_finding_title(f), _finding_plain(f) or "See portal for remediation steps."))
    return out


def _snapshots_baseline_latest(
    client_id: str, onboarded_at: datetime
) -> tuple[set[str] | None, set[str] | None, int | None, int | None]:
    """First snapshot at/after onboarding and latest snapshot; return finding key sets and scores."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_shield_monitor_snapshots",
        headers=_headers(),
        params={
            "client_id": f"eq.{client_id}",
            "select": "finding_keys,hawk_score,scanned_at",
            "order": "scanned_at.asc",
            "limit": "200",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        return None, None, None, None
    rows = r.json() or []
    onboarded_iso = onboarded_at.isoformat()
    baseline_row = None
    for row in rows:
        sa = _parse_ts(row.get("scanned_at"))
        if sa and sa >= onboarded_at:
            baseline_row = row
            break
    if baseline_row is None and rows:
        baseline_row = rows[0]

    r2 = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_shield_monitor_snapshots",
        headers=_headers(),
        params={
            "client_id": f"eq.{client_id}",
            "select": "finding_keys,hawk_score,scanned_at",
            "order": "scanned_at.desc",
            "limit": "1",
        },
        timeout=30.0,
    )
    latest_row = (r2.json() or [None])[0] if r2.status_code == 200 else None

    b_keys: set[str] = set(baseline_row.get("finding_keys") or []) if baseline_row else set()
    l_keys: set[str] = set(latest_row.get("finding_keys") or []) if latest_row else set()
    bs = baseline_row.get("hawk_score") if baseline_row else None
    ls = latest_row.get("hawk_score") if latest_row else None
    b_score = int(bs) if isinstance(bs, int) else None
    l_score = int(ls) if isinstance(ls, int) else None
    return b_keys, l_keys, b_score, l_score


def _critical_unverified_count(findings: list[dict[str, Any]]) -> int:
    n = 0
    for f in findings:
        if str(f.get("severity") or "").lower() != "critical":
            continue
        if f.get("verified_at"):
            continue
        n += 1
    return n


def run_shield_onboarding_sequences() -> dict[str, Any]:
    """
    For clients with onboarded_at set (Shield), send Day 1 (24h+), Day 3 (72h+), Day 7 (7d+) touchpoints once each.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}

    now = datetime.now(timezone.utc)
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={
            "onboarded_at": "not.is.null",
            "status": "eq.active",
            "select": (
                "id,domain,company_name,prospect_id,onboarded_at,certification_eligible_at,"
                "onboarding_call_booked_at,onboarding_day1_sent_at,onboarding_day3_sent_at,"
                "onboarding_day7_sent_at,week_one_score_start,week_one_score_end"
            ),
            "limit": "500",
        },
        timeout=60.0,
    )
    if r.status_code >= 400:
        return {"ok": False, "error": r.text[:400]}
    clients = r.json() or []

    base = (CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com").rstrip("/")
    portal_url = f"{base}/portal"
    portal_login = f"{base}/portal/login"

    stats: dict[str, Any] = {
        "ok": True,
        "clients_scanned": len(clients),
        "day1": 0,
        "day3": 0,
        "day7": 0,
        "errors": [],
    }
    err_list: list[str] = stats["errors"]

    for c in clients:
        cid = str(c["id"])
        onboarded = _parse_ts(c.get("onboarded_at"))
        if not onboarded:
            continue

        d1_at = onboarded + timedelta(hours=24)
        d3_at = onboarded + timedelta(hours=72)
        d7_at = onboarded + timedelta(days=7)

        prospect_id = c.get("prospect_id")
        prospect_id_s = str(prospect_id) if prospect_id else None

        email, prospect, phone = _portal_and_prospect(cid, prospect_id_s)
        first = _first_name(prospect)
        company = (c.get("company_name") or c.get("domain") or "Your business")[:200]

        findings, scan_score = _latest_prospect_scan(prospect_id_s)
        cert_end = _parse_ts(c.get("certification_eligible_at"))
        days_left = 0
        if cert_end:
            days_left = max(0, (cert_end - now).days)

        # --- Day 1 ---
        if (
            now >= d1_at
            and not c.get("onboarding_day1_sent_at")
        ):
            try:
                if not email:
                    err_list.append(f"{cid}: day1 skipped — no portal email on client_portal_profiles")
                else:
                    tops = _top_findings_plain(findings, 3)
                    shield_day1_findings_email(
                        to_email=email,
                        company_name=str(company),
                        portal_url=portal_login,
                        booking_url=CAL_COM_BOOKING_URL,
                        top_findings=tops,
                    )
                    if not c.get("onboarding_call_booked_at") and phone:
                        send_sms(
                            phone,
                            f"Hi {first} your onboarding call with HAWK is not booked yet. "
                            "This is where we walk you through your findings and fix plan. "
                            f"Book here: {CAL_COM_BOOKING_URL}",
                        )
                    httpx.patch(
                        f"{SUPABASE_URL}/rest/v1/clients",
                        headers=_headers(),
                        params={"id": f"eq.{cid}"},
                        json={"onboarding_day1_sent_at": now.isoformat()},
                        timeout=20.0,
                    ).raise_for_status()
                    stats["day1"] += 1
            except Exception as e:
                logger.exception("day1 failed client=%s", cid)
                err_list.append(f"{cid} day1: {e}")

        # --- Day 3 ---
        if now >= d3_at and not c.get("onboarding_day3_sent_at"):
            try:
                b_keys, l_keys, b_score, l_score = _snapshots_baseline_latest(cid, onboarded)
                resolved_n = 0
                if b_keys is not None and l_keys is not None:
                    resolved_n = len(b_keys - l_keys)
                score_was = b_score
                score_now = l_score if l_score is not None else (scan_score or 0)
                if score_was is None:
                    ws = c.get("week_one_score_start")
                    score_was = int(ws) if isinstance(ws, int) else (scan_score or 0)

                improved = resolved_n > 0 or (
                    isinstance(b_score, int)
                    and isinstance(l_score, int)
                    and l_score > b_score
                )
                if improved:
                    body = (
                        f"Great work — you fixed {resolved_n} finding(s). "
                        f"Score improved from {score_was} to {score_now}. "
                        f"{days_left} days until HAWK Certified."
                    )
                else:
                    crit = _critical_unverified_count(findings)
                    if crit > 0:
                        body = (
                            f"Hi {first} your critical findings have not been resolved yet. "
                            "Your guarantee requires fixes within 24-48 hours. Need help? Reply to this message."
                        )
                    else:
                        body = (
                            f"Hi {first} we have not seen verified fixes yet on your top priorities. "
                            "Your guarantee requires timely action within 24–48 hours on critical items. Need help? Reply to this message."
                        )

                if phone:
                    send_sms(phone, body)
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/clients",
                    headers=_headers(),
                    params={"id": f"eq.{cid}"},
                    json={"onboarding_day3_sent_at": now.isoformat()},
                    timeout=20.0,
                ).raise_for_status()
                stats["day3"] += 1
            except Exception as e:
                logger.exception("day3 failed client=%s", cid)
                err_list.append(f"{cid} day3: {e}")

        # --- Day 7 ---
        if now >= d7_at and not c.get("onboarding_day7_sent_at"):
            try:
                b_keys, l_keys, b_sc, l_sc = _snapshots_baseline_latest(cid, onboarded)
                fixed = len((b_keys or set()) - (l_keys or set())) if b_keys is not None and l_keys is not None else 0
                remaining = len(l_keys or []) if l_keys is not None else len(findings)

                score_was = c.get("week_one_score_start")
                score_was_i = int(score_was) if isinstance(score_was, int) else None
                if score_was_i is None:
                    score_was_i = b_sc if isinstance(b_sc, int) else (scan_score or 0)
                score_now_i = l_sc if isinstance(l_sc, int) else (scan_score or 0)

                elapsed = (now - onboarded).days
                progress_pct = min(100, int(min(90, max(0, elapsed)) / 90 * 100))

                wa = (
                    f"HAWK Week One Summary — {company} Score: {score_now_i}/100 "
                    f"(was {score_was_i} at signup) Findings fixed: {fixed} "
                    f"Findings remaining: {remaining} Guarantee: ACTIVE "
                    f"Days until HAWK Certified: {days_left}"
                )
                if phone:
                    send_sms(phone, wa)

                if email:
                    shield_day7_week_summary_email(
                        to_email=email,
                        company_name=str(company),
                        portal_url=portal_login,
                        score_now=score_now_i,
                        score_was=score_was_i,
                        findings_fixed=fixed,
                        findings_remaining=remaining,
                        days_until_certified=days_left,
                        progress_pct=progress_pct,
                    )

                patch7: dict[str, Any] = {
                    "onboarding_day7_sent_at": now.isoformat(),
                    "week_one_score_end": score_now_i,
                }
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/clients",
                    headers=_headers(),
                    params={"id": f"eq.{cid}"},
                    json=patch7,
                    timeout=20.0,
                ).raise_for_status()
                stats["day7"] += 1
            except Exception as e:
                logger.exception("day7 failed client=%s", cid)
                err_list.append(f"{cid} day7: {e}")

    return stats

