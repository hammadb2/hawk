"""Closer-briefing SMS payload for the Cal.com booking webhook.

When a prospect books a call we want the closer (Hammad + Kevin) to walk in
with the three most critical vulnerabilities we found on the prospect's
domain, the Hawk Score, and the vertical. Short enough to read on a phone
lock screen, detailed enough to sound prepared on the call.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from config import CRM_PUBLIC_BASE_URL, SUPABASE_URL

logger = logging.getLogger(__name__)


def _sb_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {key}"}


# Severity ordering used when we have to hand-pick top findings from a jsonb blob.
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _coerce_severity(value: Any) -> int:
    if isinstance(value, int):
        return value
    return _SEVERITY_RANK.get(str(value).strip().lower(), 0)


def _summarise_finding(raw: Any) -> str | None:
    """Normalise a scan-finding row (varied shapes across our scanners) to one line."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.strip()[:120] or None
    if not isinstance(raw, dict):
        return None
    for key in ("title", "name", "label", "finding", "summary", "message", "description"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:120]
    # Common shape: {"id": "dmarc_missing", "severity": "high"}
    ident = raw.get("id") or raw.get("key") or raw.get("type")
    if isinstance(ident, str) and ident.strip():
        return ident.replace("_", " ").title()[:120]
    return None


def _extract_top_vulns(findings: Any, limit: int = 3) -> list[str]:
    """Return ``limit`` highest-severity finding labels from a jsonb blob."""
    if findings is None:
        return []
    items: list[tuple[int, str]] = []

    # Shape A: {"rows": [...], "critical": 2, "high": 5, ...}
    if isinstance(findings, dict):
        rows = findings.get("rows") or findings.get("items") or findings.get("findings")
        if isinstance(rows, list):
            for row in rows:
                label = _summarise_finding(row)
                if not label:
                    continue
                severity = (
                    row.get("severity") if isinstance(row, dict) else None
                )
                items.append((_coerce_severity(severity), label))
        # Shape B: counts only — {"critical": 3, "high": 2, ...}
        if not items:
            for sev in ("critical", "high", "medium"):
                count = findings.get(sev)
                if isinstance(count, int) and count > 0:
                    label = f"{count} {sev}-severity findings"
                    items.append((_coerce_severity(sev), label))

    # Shape C: ["DMARC missing", "TLS 1.0", ...] or list of dicts
    if isinstance(findings, list):
        for row in findings:
            label = _summarise_finding(row)
            if not label:
                continue
            severity = row.get("severity") if isinstance(row, dict) else None
            items.append((_coerce_severity(severity), label))

    # dedupe + keep highest-severity wins
    seen: dict[str, int] = {}
    for rank, label in items:
        if label not in seen or seen[label] < rank:
            seen[label] = rank
    ranked = sorted(seen.items(), key=lambda t: (-t[1], t[0]))
    return [label for label, _ in ranked[:limit]]


def fetch_briefing(prospect_id: str) -> dict[str, Any]:
    """Return prospect briefing context used in closer SMS + prospect confirmation."""
    briefing: dict[str, Any] = {
        "company_name": "",
        "domain": "",
        "vertical": "",
        "hawk_score": None,
        "top_vulns": [],
        "prospect_url": "",
        "assigned_rep_id": None,
    }
    if not SUPABASE_URL or not prospect_id:
        return briefing
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "id": f"eq.{prospect_id}",
                "select": "id,domain,company_name,vertical,hawk_score,assigned_rep_id",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json()
    except Exception:
        logger.exception("fetch_briefing: prospect load failed id=%s", prospect_id)
        rows = []
    if not rows:
        return briefing

    row = rows[0]
    briefing.update({
        "company_name": row.get("company_name") or row.get("domain") or "Prospect",
        "domain": row.get("domain") or "",
        "vertical": row.get("vertical") or "",
        "hawk_score": row.get("hawk_score"),
        "assigned_rep_id": row.get("assigned_rep_id"),
    })
    base = (CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com").rstrip("/")
    briefing["prospect_url"] = f"{base}/crm/prospects/{prospect_id}"

    # Most recent scan row for actual findings
    try:
        scan = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
            headers=_sb_headers(),
            params={
                "prospect_id": f"eq.{prospect_id}",
                "select": "hawk_score,findings,created_at",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=15.0,
        )
        scan.raise_for_status()
        scans = scan.json()
    except Exception:
        logger.exception("fetch_briefing: scan load failed id=%s", prospect_id)
        scans = []
    if scans:
        scan_row = scans[0]
        if briefing.get("hawk_score") is None:
            briefing["hawk_score"] = scan_row.get("hawk_score")
        briefing["top_vulns"] = _extract_top_vulns(scan_row.get("findings"))

    # Fallback: pull from aria_lead_inventory.vulnerability_found
    if not briefing["top_vulns"]:
        try:
            lead_r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
                headers=_sb_headers(),
                params={
                    "prospect_id": f"eq.{prospect_id}",
                    "select": "vulnerability_found,hawk_score",
                    "limit": "1",
                },
                timeout=15.0,
            )
            lead_r.raise_for_status()
            leads = lead_r.json()
        except Exception:
            leads = []
        if leads:
            vuln = (leads[0].get("vulnerability_found") or "").strip()
            if vuln:
                briefing["top_vulns"] = [vuln[:120]]
            if briefing.get("hawk_score") is None:
                briefing["hawk_score"] = leads[0].get("hawk_score")

    return briefing


def render_sms(briefing: dict[str, Any], attendee_name: str | None, time_note: str) -> str:
    """Format the closer SMS. Budgeted at ~600 chars so two SMS segments max."""
    name = attendee_name or "Prospect"
    company = briefing.get("company_name") or "Prospect"
    vertical = briefing.get("vertical") or "—"
    score = briefing.get("hawk_score")
    score_str = f"{score}/100" if score is not None else "n/a"
    vulns = briefing.get("top_vulns") or ["(no scan findings available)"]
    vuln_lines = "\n".join(f"- {v}" for v in vulns[:3])
    url = briefing.get("prospect_url") or ""

    return (
        f"HAWK — CALL BOOKED\n"
        f"{name} @ {company} ({vertical})\n"
        f"Hawk Score: {score_str}\n"
        f"Time: {time_note}\n"
        f"Top vulns:\n{vuln_lines}\n"
        f"Brief: {url}"
    )[:1500]


def render_confirmation_email(briefing: dict[str, Any], time_note: str, booking_link: str | None) -> tuple[str, str]:
    """Return (subject, html) for the prospect's booking confirmation email."""
    company = briefing.get("company_name") or "your practice"
    top = briefing.get("top_vulns") or []
    finding_line = top[0] if top else "the findings we picked up on your domain"
    subject = f"Confirmed — our call on {time_note}"
    html = f"""
<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:560px;line-height:1.55;color:#0b1220;">
  <p>Hi,</p>
  <p>Confirming our short call on <strong>{time_note}</strong>.</p>
  <p>What to expect: 15 minutes, screen-share walkthrough of what our scanner
  picked up on your domain, straight answers on how HAWK would close those
  gaps, and we wrap with a clear next step (no pressure either way).</p>
  <p>Specifically, we'll spend the first few minutes on
  <strong>{finding_line}</strong> — that's the finding on {company} I'd
  most want to get in front of you.</p>
  <p>{('Reschedule/cancel: ' + booking_link) if booking_link else 'If something comes up, just reply to this email.'}</p>
  <p>Talk then.<br>Hammad<br>HAWK Security</p>
</div>
""".strip()
    return subject, html


__all__ = ["fetch_briefing", "render_sms", "render_confirmation_email"]
