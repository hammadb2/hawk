"""2A — Daily Shield client rescan: diff vs prior snapshot, alert on new critical/high only."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from config import CRM_PUBLIC_BASE_URL
from services.crm_portal_email import send_resend
from services.crm_twilio import send_whatsapp
from services.scanner import enqueue_async_scan, poll_scan_job

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
    if mc >= 99700:
        return True
    return False


def _finding_key(f: dict[str, Any]) -> str:
    layer = str(f.get("layer") or "").lower()[:80]
    title = str(f.get("title") or "").lower()[:200]
    asset = str(f.get("affected_asset") or "").lower()[:200]
    return f"{layer}|{title}|{asset}"


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


def _alertable_new(
    prev_keys: set[str],
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in findings:
        sev = str(f.get("severity") or "").lower()
        if sev not in ("critical", "high"):
            continue
        k = _finding_key(f)
        if k not in prev_keys:
            out.append(f)
    return out


def _latest_snapshot(client_id: str, domain: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_shield_monitor_snapshots",
        headers=_headers(),
        params={
            "client_id": f"eq.{client_id}",
            "domain": f"eq.{domain}",
            "select": "finding_keys,scanned_at",
            "order": "scanned_at.desc",
            "limit": "1",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.error("snapshot fetch failed: %s", r.text[:400])
        return None
    rows = r.json()
    return rows[0] if rows else None


def _insert_snapshot(
    client_id: str,
    domain: str,
    *,
    score: int | None,
    grade: str | None,
    keys: list[str],
    detail: dict[str, Any],
) -> None:
    body = {
        "client_id": client_id,
        "domain": domain,
        "hawk_score": score,
        "grade": grade,
        "finding_keys": keys,
        "detail": detail,
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_shield_monitor_snapshots",
        headers=_headers(),
        json=body,
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.error("snapshot insert failed: %s", r.text[:500])


def _insert_event(
    client_id: str,
    *,
    channel: str,
    summary: str,
    keys: list[str],
    detail: dict[str, Any],
) -> None:
    body = {
        "client_id": client_id,
        "channel": channel,
        "summary": summary,
        "new_finding_keys": keys,
        "detail": detail,
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_shield_monitor_events",
        headers=_headers(),
        json=body,
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.error("monitor event insert failed: %s", r.text[:500])


def _normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().replace("whatsapp:", "")
    if s.startswith("+"):
        digits = "+" + "".join(c for c in s[1:] if c.isdigit())
        return digits if len(digits) > 8 else None
    d = "".join(c for c in s if c.isdigit())
    return f"+{d}" if len(d) > 8 else None


def run_daily_shield_rescans() -> dict[str, Any]:
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "implemented": False, "error": "supabase not configured", "processed": 0}

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={
            "status": "eq.active",
            "select": "id,domain,company_name,plan,mrr_cents,prospect_id",
            "limit": "500",
        },
        timeout=60.0,
    )
    r.raise_for_status()
    clients: list[dict[str, Any]] = r.json()

    shield_clients = [c for c in clients if _is_shield_plan(c.get("plan"), c.get("mrr_cents"))]
    base = (CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com").rstrip("/")

    processed = 0
    alerts_whatsapp = 0
    alerts_email = 0
    errors: list[str] = []

    for c in shield_clients:
        cid = str(c["id"])
        domain = (c.get("domain") or "").strip().lower()
        if not domain:
            errors.append(f"client {cid}: no domain")
            continue
        company = (c.get("company_name") or domain).strip()

        industry = None
        phone = None
        pid = c.get("prospect_id")
        if pid:
            pr = httpx.get(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_headers(),
                params={"id": f"eq.{pid}", "select": "industry,phone", "limit": "1"},
                timeout=20.0,
            )
            if pr.status_code == 200:
                prow = (pr.json() or [{}])[0]
                industry = prow.get("industry")
                phone = _normalize_phone(prow.get("phone"))

        portal_email = None
        cpp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
            headers=_headers(),
            params={"client_id": f"eq.{cid}", "select": "email", "limit": "1"},
            timeout=20.0,
        )
        if cpp.status_code == 200 and cpp.json():
            portal_email = (cpp.json()[0] or {}).get("email")

        prev = _latest_snapshot(cid, domain)
        prev_keys: set[str] = set(prev.get("finding_keys") or []) if prev else set()
        baseline_only = prev is None

        try:
            job_id = enqueue_async_scan(
                domain,
                industry=str(industry).strip() if industry else None,
                company_name=company,
            )
            result = poll_scan_job(job_id, timeout_sec=720.0, interval_sec=3.0)
        except Exception as e:
            logger.exception("shield scan failed client=%s domain=%s", cid, domain)
            errors.append(f"{domain}: {e}")
            continue

        findings = _findings_list(result.get("findings"))
        keys = [_finding_key(f) for f in findings]
        score = result.get("score")
        grade = result.get("grade")

        new_alertable = _alertable_new(prev_keys, findings)

        _insert_snapshot(
            cid,
            domain,
            score=int(score) if isinstance(score, int) else None,
            grade=str(grade) if grade else None,
            keys=keys,
            detail={
                "findings_count": len(findings),
                "job_ok": True,
                "baseline_only": baseline_only,
                "new_critical_high": len(new_alertable),
            },
        )

        processed += 1

        if baseline_only or not new_alertable:
            _insert_event(
                cid,
                channel="none",
                summary="Daily scan complete — no new critical/high vs prior snapshot."
                if not baseline_only
                else "Initial Shield baseline snapshot recorded (no alert).",
                keys=[],
                detail={"domain": domain, "baseline_only": baseline_only},
            )
            continue

        titles = [str(f.get("title") or "Finding") for f in new_alertable[:5]]
        top = titles[0]
        summary = f"New critical/high exposure(s) on {domain}: {top}" + (
            f" (+{len(titles) - 1} more)" if len(titles) > 1 else ""
        )

        wa_sent = False
        em_sent = False
        if phone:
            body = (
                f"HAWK Alert — {company}\n"
                f"New critical/high finding detected on {domain}:\n{top}\n"
                f"Log in to see details and fix steps: {base}/portal"
            )
            try:
                out = send_whatsapp(phone, body)
                wa_sent = not out.get("skipped")
                if wa_sent:
                    alerts_whatsapp += 1
            except Exception:
                logger.exception("whatsapp shield alert failed client=%s", cid)

        if portal_email:
            try:
                send_resend(
                    to_email=str(portal_email),
                    subject=f"HAWK Alert — new risk on {domain}",
                    html=(
                        f"<p>Hi,</p><p>We detected <strong>new</strong> critical or high-severity exposure(s) "
                        f"on <strong>{_html_escape(domain)}</strong> during today&apos;s Shield monitoring pass.</p>"
                        f"<p><strong>First item:</strong> {_html_escape(top)}</p>"
                        f"<p><a href=\"{base}/portal\">Open your HAWK portal</a> for full details and fix guides.</p>"
                        f"<p style=\"color:#666;font-size:12px\">HAWK Security</p>"
                    ),
                )
                em_sent = True
                alerts_email += 1
            except Exception:
                logger.exception("email shield alert failed client=%s", cid)

        ch = "both" if wa_sent and em_sent else "whatsapp" if wa_sent else "email" if em_sent else "none"
        _insert_event(
            cid,
            channel=ch,
            summary=summary,
            keys=[_finding_key(f) for f in new_alertable],
            detail={"titles": titles, "domain": domain},
        )

    return {
        "ok": True,
        "implemented": True,
        "shield_clients": len(shield_clients),
        "processed": processed,
        "alerts_whatsapp": alerts_whatsapp,
        "alerts_email": alerts_email,
        "errors": errors[:20],
    }


def _html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
