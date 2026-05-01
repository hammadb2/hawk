"""Award portal gamification milestones (hawk_certified, thirty_days_clean, …).

The portal renders these as the 7-step "HAWK Certified" tracker. Each key here
maps to an entry in :data:`HAWK_CERTIFIED_STEPS` (declared at module bottom).
Detection helpers are pure functions of a scan row and stay exported so tests
can call them without hitting Supabase.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        raw = str(raw).replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _findings_list(scan: dict[str, Any]) -> list[dict[str, Any]]:
    raw = scan.get("findings")
    if isinstance(raw, dict):
        fl = raw.get("findings")
        if isinstance(fl, list):
            return [x for x in fl if isinstance(x, dict)]
    return []


def _severity_rank(s: str) -> int:
    x = (s or "").lower()
    return {"critical": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 4}.get(x, 5)


def _scan_has_critical_or_high(scan: dict[str, Any]) -> bool:
    for f in _findings_list(scan):
        if _severity_rank(str(f.get("severity") or "")) <= 1:
            return True
    return False


def _scan_has_critical(scan: dict[str, Any]) -> bool:
    for f in _findings_list(scan):
        if _severity_rank(str(f.get("severity") or "")) == 0:
            return True
    return False


def _find_finding(scan: dict[str, Any], title_substr: str) -> dict[str, Any] | None:
    needle = title_substr.lower()
    for f in _findings_list(scan):
        if needle in str(f.get("title") or "").lower():
            return f
    return None


def is_dmarc_strict(scan: dict[str, Any]) -> bool:
    """DMARC policy is ``quarantine`` or ``reject`` (the two strict policies).

    Only inspects ``technical_detail`` (which holds the literal DNS TXT record
    per :mod:`hawk-scanner-v2.app.analysis.email_security`); the human-readable
    ``description`` mentions both policies as recommendations even when the
    actual policy is ``none`` and would produce false positives.
    """
    f = _find_finding(scan, "dmarc")
    if not f:
        return False
    record = str(f.get("technical_detail") or "").lower()
    if not record:
        return False
    if re.search(r"\bp\s*=\s*reject\b", record):
        return True
    if re.search(r"\bp\s*=\s*quarantine\b", record):
        return True
    return False


def is_spf_strict(scan: dict[str, Any]) -> bool:
    """SPF record ends in ``-all`` (strict fail). ``~all`` does not count.

    Anchored to the end of the trimmed record (after stripping wrapping
    quotes and whitespace). Substring matching is unsafe because include
    domains like ``include:mail-allservices.example.com ~all`` contain
    ``-all`` inside the hostname.

    Only inspects ``technical_detail`` (the literal SPF DNS record) — the
    ``description`` for a ``~all`` softfail explicitly recommends ``-all``
    so substring-matching it would always falsely award the milestone.
    """
    f = _find_finding(scan, "spf")
    if not f:
        return False
    record = str(f.get("technical_detail") or "").lower().strip().strip('"').strip()
    return record.endswith("-all")


def _insurance_readiness_pct(scan: dict[str, Any]) -> int | None:
    """Return the integer readiness percentage if present.

    Mirrors :func:`services.aria_post_scan_filter._insurance_readiness_pct` —
    ``compute_insurance_readiness`` (in hawk-scanner-v2) emits
    ``{"readiness_pct": int, ...}`` and ``aria_sla_auto_scan`` stashes it
    inside the ``findings`` JSON blob so we can read it without a schema
    migration. Older scan rows kept it on ``raw_layers`` instead, hence
    the fallback.
    """
    for container_key in ("findings", "raw_layers"):
        container = scan.get(container_key)
        if not isinstance(container, dict):
            continue
        ins = container.get("insurance_readiness")
        if isinstance(ins, dict):
            # Check keys in priority order with explicit ``is None`` so a real
            # ``readiness_pct: 0`` doesn't fall through to a stale alias.
            for key in ("readiness_pct", "score", "overall", "pct"):
                pct = ins.get(key)
                if pct is None:
                    continue
                if isinstance(pct, (int, float)):
                    return int(pct)
                try:
                    return int(pct)
                except (TypeError, ValueError):
                    break
        elif isinstance(ins, (int, float)):
            return int(ins)
    return None


def is_insurance_readiness_above_80(scan: dict[str, Any]) -> bool:
    pct = _insurance_readiness_pct(scan)
    return pct is not None and pct >= 80


def _milestone_exists(client_id: str, key: str) -> bool:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_security_milestones",
        headers=_sb(),
        params={
            "client_id": f"eq.{client_id}",
            "milestone_key": f"eq.{key}",
            "select": "id",
            "limit": "1",
        },
        timeout=15.0,
    )
    if r.status_code != 200:
        return False
    return bool(r.json())


def _insert_milestone(client_id: str, key: str, metadata: dict[str, Any]) -> None:
    mr = httpx.post(
        f"{SUPABASE_URL}/rest/v1/client_security_milestones",
        headers=_sb(),
        json={"client_id": client_id, "milestone_key": key, "metadata": metadata},
        timeout=15.0,
    )
    if mr.status_code >= 400 and mr.status_code != 409:
        logger.warning("milestone insert %s: %s", key, mr.text[:200])


def ensure_portal_milestones(client_id: str, prospect_id: str | None) -> None:
    """
    Insert HAWK Certified tracker milestones when criteria are met (idempotent via unique constraint).

    Milestones awarded here:
      - ``hawk_certified``                 — read off ``clients.certified_at``.
      - ``dmarc_strict``                   — latest scan shows DMARC ``p=quarantine`` or ``p=reject``.
      - ``spf_strict``                     — latest scan shows SPF ending in ``-all``.
      - ``insurance_readiness_above_80``   — latest scan emits readiness ≥ 80%.
      - ``fourteen_days_zero_critical``    — ≥ 14 days since first scan and latest scan has no critical.
      - ``thirty_days_clean``              — ≥ 30 days since first scan and latest scan has no critical/high.

    ``first_critical_fix`` and ``score_above_70`` are emitted from
    ``crm_portal_api`` when a fix is verified, not here.
    """
    if not SUPABASE_URL or not SERVICE_KEY or not client_id:
        return

    cl = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={"id": f"eq.{client_id}", "select": "certified_at", "limit": "1"},
        timeout=15.0,
    )
    if cl.status_code != 200:
        return
    crow = (cl.json() or [None])[0] or {}
    if crow.get("certified_at") and not _milestone_exists(client_id, "hawk_certified"):
        _insert_milestone(client_id, "hawk_certified", {"source": "certified_at"})

    if not prospect_id:
        return

    sc = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers=_sb(),
        params={
            "prospect_id": f"eq.{prospect_id}",
            "select": "id,created_at,findings",
            "order": "created_at.asc",
            "limit": "200",
        },
        timeout=30.0,
    )
    if sc.status_code != 200:
        return
    scans = sc.json() or []
    if not scans:
        return

    latest = scans[-1]

    # Per-scan posture milestones (no tenure requirement).
    if is_dmarc_strict(latest) and not _milestone_exists(client_id, "dmarc_strict"):
        _insert_milestone(client_id, "dmarc_strict", {"scan_id": latest.get("id")})
    if is_spf_strict(latest) and not _milestone_exists(client_id, "spf_strict"):
        _insert_milestone(client_id, "spf_strict", {"scan_id": latest.get("id")})
    if is_insurance_readiness_above_80(latest) and not _milestone_exists(
        client_id, "insurance_readiness_above_80"
    ):
        _insert_milestone(
            client_id,
            "insurance_readiness_above_80",
            {"scan_id": latest.get("id"), "pct": _insurance_readiness_pct(latest)},
        )

    # Tenure-gated milestones.
    now = datetime.now(timezone.utc)
    first_at = _parse_ts(scans[0].get("created_at"))
    if not first_at:
        return
    if first_at.tzinfo is None:
        first_at = first_at.replace(tzinfo=timezone.utc)
    age = now - first_at

    if age >= timedelta(days=14) and not _scan_has_critical(latest):
        if not _milestone_exists(client_id, "fourteen_days_zero_critical"):
            _insert_milestone(
                client_id,
                "fourteen_days_zero_critical",
                {"latest_scan_id": latest.get("id"), "rule": "14d_tenure_no_critical_on_latest"},
            )

    if age >= timedelta(days=30) and not _scan_has_critical_or_high(latest):
        if not _milestone_exists(client_id, "thirty_days_clean"):
            _insert_milestone(
                client_id,
                "thirty_days_clean",
                {"latest_scan_id": latest.get("id"), "rule": "30d_tenure_no_ch_on_latest"},
            )


# ---------------------------------------------------------------------------
# 7-step "HAWK Certified" tracker registry. Order matters — frontend renders
# top-to-bottom. Add/edit ``HAWK_CERTIFIED_STEPS`` when the spec changes.
# ---------------------------------------------------------------------------

HAWK_CERTIFIED_STEPS: list[dict[str, str]] = [
    {
        "key": "first_critical_fix",
        "title": "Verify your first critical fix",
        "blurb": "Resolve and rescan one Critical finding from your scan.",
    },
    {
        "key": "spf_strict",
        "title": "Lock down SPF (-all)",
        "blurb": "Tighten SPF to a hard-fail policy so spoofers can't impersonate you.",
    },
    {
        "key": "dmarc_strict",
        "title": "Move DMARC to quarantine or reject",
        "blurb": "Stop spoofed mail at the recipient. p=none doesn't protect anyone.",
    },
    {
        "key": "insurance_readiness_above_80",
        "title": "Reach 80% insurance readiness",
        "blurb": "Hit the threshold most cyber-liability underwriters look for.",
    },
    {
        "key": "score_above_70",
        "title": "Reach a HAWK score of 70+",
        "blurb": "70+ means you've cleared the major exposure categories.",
    },
    {
        "key": "fourteen_days_zero_critical",
        "title": "14 days with zero criticals",
        "blurb": "Two clean weeks. Drift hasn't pulled new criticals back into scope.",
    },
    {
        "key": "thirty_days_clean",
        "title": "30 days clean (no critical or high)",
        "blurb": "A full month of clean scans. You qualify for HAWK Certified.",
    },
]


def hawk_certified_progress(
    milestones: list[dict[str, Any]] | None,
    *,
    certified_at: str | None = None,
) -> dict[str, Any]:
    """Project a list of milestone rows into the 7-step tracker shape.

    Returns ``{"steps": [...], "completed": int, "total": int, "certified_at": str|None}``
    where each step has ``key``, ``title``, ``blurb``, ``done`` (bool), and ``achieved_at``
    (ISO string or None). Designed to be safe to call with an empty/None list.
    """
    by_key: dict[str, str] = {}
    for m in milestones or []:
        if not isinstance(m, dict):
            continue
        k = m.get("milestone_key")
        ts = m.get("achieved_at")
        if isinstance(k, str) and isinstance(ts, str) and k not in by_key:
            by_key[k] = ts

    steps: list[dict[str, Any]] = []
    for entry in HAWK_CERTIFIED_STEPS:
        achieved = by_key.get(entry["key"])
        steps.append({
            "key": entry["key"],
            "title": entry["title"],
            "blurb": entry["blurb"],
            "done": achieved is not None,
            "achieved_at": achieved,
        })
    completed = sum(1 for s in steps if s["done"])
    return {
        "steps": steps,
        "completed": completed,
        "total": len(steps),
        "certified_at": certified_at,
    }
