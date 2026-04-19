"""
Progressive writes to CRM `prospects` during ARIA discovery and pipeline steps.

Uses service role REST (same as aria_pipeline). Match rows by `domain` (unique).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")

_CHUNK = 80


def _sb_headers(*, merge_upsert: bool = False) -> dict[str, str]:
    prefer = "return=minimal"
    if merge_upsert:
        prefer = "return=minimal,resolution=merge-duplicates"
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _normalize_domain(raw: str) -> str:
    d = (raw or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p) :]
    d = d.split("/")[0].split("?")[0].strip()
    if "@" in d:
        d = d.split("@")[-1]
    if d.startswith("www."):
        d = d[4:]
    return d


def _configured() -> bool:
    return bool(SUPABASE_URL and SERVICE_KEY)


def bulk_upsert_discovered_prospects(
    leads: list[dict[str, Any]],
    *,
    pipeline_run_id: str | None,
    source: str,
) -> None:
    """Insert or merge prospects after Google Maps (Actor 1) + dedupe; pipeline_status = discovered."""
    if not _configured() or not leads:
        return

    rows: list[dict[str, Any]] = []
    for lead in leads:
        domain = _normalize_domain(str(lead.get("domain") or ""))
        if not domain:
            continue
        row: dict[str, Any] = {
            "domain": domain,
            "company_name": lead.get("business_name") or lead.get("company_name") or domain,
            "industry": ((lead.get("vertical") or "")[:200] or None),
            "city": lead.get("city"),
            "province": lead.get("province"),
            "address": lead.get("address"),
            "phone": lead.get("phone"),
            "google_rating": lead.get("google_rating"),
            "review_count": lead.get("review_count"),
            "pipeline_status": "discovered",
            "source": source,
            "stage": "new",
        }
        row["lead_score"] = int(lead.get("lead_score") or 0)
        row["hawk_score"] = 0
        if pipeline_run_id:
            row["pipeline_run_id"] = pipeline_run_id
        rows.append({k: v for k, v in row.items() if v is not None})

    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i : i + _CHUNK]
        try:
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(merge_upsert=True),
                params={"on_conflict": "domain"},
                json=chunk,
                timeout=60.0,
            )
            if r.status_code >= 400:
                logger.warning("Prospects discovered upsert failed: %s %s", r.status_code, r.text[:400])
        except Exception as exc:
            logger.warning("Prospects discovered upsert error: %s", exc)


def bulk_upsert_enriched_prospects(
    leads: list[dict[str, Any]],
    *,
    pipeline_run_id: str | None,
    source: str,
) -> None:
    """Upsert leads that already have email (e.g. Apollo fallback) as pipeline_status = enriched."""
    if not _configured() or not leads:
        return

    rows: list[dict[str, Any]] = []
    for lead in leads:
        domain = _normalize_domain(str(lead.get("domain") or ""))
        email = (lead.get("contact_email") or "").strip().lower()
        if not domain or not email or "@" not in email:
            continue
        row: dict[str, Any] = {
            "domain": domain,
            "company_name": lead.get("business_name") or lead.get("company_name") or domain,
            "industry": ((lead.get("vertical") or "")[:200] or None),
            "city": lead.get("city"),
            "province": lead.get("province"),
            "address": lead.get("address"),
            "phone": lead.get("phone"),
            "contact_email": email,
            "contact_name": lead.get("contact_name") or None,
            "google_rating": lead.get("google_rating"),
            "review_count": lead.get("review_count"),
            "email_finder": (lead.get("email_finder") or "")[:200] or None,
            "pipeline_status": "enriched",
            "source": source,
            "stage": "new",
        }
        row["lead_score"] = int(lead.get("lead_score") or 0)
        row["hawk_score"] = 0
        if pipeline_run_id:
            row["pipeline_run_id"] = pipeline_run_id
        rows.append({k: v for k, v in row.items() if v is not None})

    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i : i + _CHUNK]
        try:
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(merge_upsert=True),
                params={"on_conflict": "domain"},
                json=chunk,
                timeout=60.0,
            )
            if r.status_code >= 400:
                logger.warning("Prospects enriched upsert failed: %s %s", r.status_code, r.text[:400])
        except Exception as exc:
            logger.warning("Prospects enriched upsert error: %s", exc)


def patch_prospect_by_domain(domain: str, fields: dict[str, Any]) -> None:
    if not _configured():
        return
    d = _normalize_domain(domain)
    if not d:
        return
    body = {k: v for k, v in fields.items() if v is not None}
    if not body:
        return
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"domain": f"eq.{d}"},
            json=body,
            timeout=20.0,
        )
        if r.status_code >= 400:
            logger.debug("Prospect patch domain=%s status=%s body=%s", d, r.status_code, r.text[:300])
    except Exception as exc:
        logger.debug("Prospect patch failed domain=%s: %s", d, exc)


def sync_prospects_after_email_merge(
    with_email: list[dict[str, Any]],
    without_email: list[dict[str, Any]],
) -> None:
    """After Apify actors 2–4 merge: mark enriched or leave discovered (no email)."""
    for lead in with_email:
        domain = str(lead.get("domain") or "")
        patch_prospect_by_domain(
            domain,
            {
                "contact_email": (lead.get("contact_email") or "").strip().lower() or None,
                "contact_name": lead.get("contact_name") or None,
                "email_finder": (lead.get("email_finder") or "")[:500] or None,
                "pipeline_status": "enriched",
                "lead_score": int(lead.get("lead_score") or 0) or None,
            },
        )
    for lead in without_email:
        domain = str(lead.get("domain") or "")
        patch_prospect_by_domain(domain, {"pipeline_status": "discovered"})


def zb_result_to_text(zb: Any) -> str:
    if zb is None:
        return ""
    if isinstance(zb, str):
        return zb[:8000]
    try:
        return json.dumps(zb, default=str)[:8000]
    except Exception:
        return str(zb)[:8000]


def sync_prospect_zerobounce_chat(
    domain: str,
    *,
    zb_payload: Any,
    zb_status: str,
    pipeline_ok: bool,
) -> None:
    """On-demand pipeline ZeroBounce: verified or suppressed on prospects."""
    text = zb_result_to_text(zb_payload)
    if pipeline_ok:
        patch_prospect_by_domain(
            domain,
            {
                "zero_bounce_result": text or zb_status,
                "pipeline_status": "verified",
            },
        )
    else:
        patch_prospect_by_domain(
            domain,
            {
                "zero_bounce_result": text or zb_status,
                "pipeline_status": "suppressed",
            },
        )


def sync_prospect_zerobounce_nightly(domain: str, zb_key: str, *, ok: bool) -> None:
    """Nightly bulk ZeroBounce enum-style result on prospects."""
    patch_prospect_by_domain(
        domain,
        {
            "zero_bounce_result": zb_key,
            "pipeline_status": "verified" if ok else "suppressed",
        },
    )


def sync_prospect_scan_chat(
    domain: str,
    *,
    vulnerability_text: str | None,
    vulnerability_type: str | None,
    hawk_score: int | None,
) -> None:
    fields: dict[str, Any] = {"pipeline_status": "scanned"}
    if vulnerability_text:
        fields["vulnerability_found"] = vulnerability_text[:10000]
    if vulnerability_type:
        fields["vulnerability_type"] = vulnerability_type[:500]
    if hawk_score is not None:
        fields["hawk_score"] = max(0, min(100, int(hawk_score)))
    patch_prospect_by_domain(domain, fields)


def sync_prospect_scan_nightly(lead: dict[str, Any]) -> None:
    domain = str(lead.get("domain") or "")
    vuln = lead.get("vulnerability_found") or ""
    vtype = str(lead.get("vulnerability_type") or "")[:500]
    if not vtype:
        scan = lead.get("scan_data") or {}
        findings = scan.get("findings") or []
        if isinstance(findings, list) and findings and isinstance(findings[0], dict):
            vtype = str(findings[0].get("severity") or findings[0].get("type") or "")[:500]
    hs = lead.get("hawk_score")
    fields: dict[str, Any] = {"pipeline_status": "scanned"}
    if vuln:
        fields["vulnerability_found"] = str(vuln)[:10000]
    if vtype:
        fields["vulnerability_type"] = vtype
    if hs is not None:
        try:
            fields["hawk_score"] = max(0, min(100, int(hs)))
        except (TypeError, ValueError):
            pass
    patch_prospect_by_domain(domain, fields)


def sync_prospect_email_ready_chat(domain: str, subject: str, body: str) -> None:
    patch_prospect_by_domain(
        domain,
        {
            "email_subject": subject[:2000] if subject else None,
            "email_body": body[:50000] if body else None,
            "pipeline_status": "ready",
        },
    )


def sync_prospect_email_ready_nightly(domain: str, subject: str, body: str) -> None:
    sync_prospect_email_ready_chat(domain, subject, body)


def sync_prospect_smartlead_chat(domain: str, campaign_id: str) -> None:
    from datetime import datetime, timezone

    patch_prospect_by_domain(
        domain,
        {
            "smartlead_campaign_id": campaign_id[:500] if campaign_id else None,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_status": "contacted",
        },
    )


def sync_prospect_smartlead_morning(domain: str, campaign_id: str) -> None:
    sync_prospect_smartlead_chat(domain, campaign_id)
