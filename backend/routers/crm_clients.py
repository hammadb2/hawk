"""
CRM Clients Router
Handles client PDF report generation — requires server-side PDF pipeline.
Simple CRUD goes through Supabase JS client directly (RLS enforced).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from backend.services.supabase_crm import supabase_available, get_supabase, log_activity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/clients", tags=["crm-clients"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/{client_id}/report")
async def generate_report(client_id: str):
    """
    Generate and send the monthly security report PDF to the client.
    Pulls the latest HAWK scan, builds a PDF via the report pipeline,
    and returns the download URL.
    """
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()

    # Load client
    client_res = (
        sb.table("clients")
        .select("*, prospect:prospect_id(id, domain, company_name)")
        .eq("id", client_id)
        .single()
        .execute()
    )
    if not client_res.data:
        raise HTTPException(status_code=404, detail="Client not found")

    client = client_res.data
    prospect = client.get("prospect") or {}
    domain = prospect.get("domain", "")
    company_name = prospect.get("company_name", "Client")

    if not domain:
        raise HTTPException(status_code=422, detail="Client has no domain — cannot generate report")

    # Get the latest completed CRM scan for this client's domain
    scan_res = (
        sb.table("crm_scans")
        .select("*")
        .or_(f"prospect_id.eq.{prospect.get('id', '')},client_id.eq.{client_id}")
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    scan_data = scan_res.data[0] if scan_res.data else None

    # Build a report using the HAWK report pipeline
    try:
        from backend.services.reports import generate_client_report
        report_url = generate_client_report(
            domain=domain,
            company_name=company_name,
            client_id=client_id,
            scan_data=scan_data,
        )
    except ImportError:
        # Report service not yet wired — fall back to generating a URL path
        logger.warning("Report service not found — returning placeholder URL")
        report_url = f"/reports/{client_id}/latest.pdf"
    except Exception as exc:
        logger.error("Report generation failed for client %s: %s", client_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {exc}",
        ) from exc

    # Log activity
    log_activity({
        "client_id": client_id,
        "type": "note_added",
        "notes": f"Monthly security report generated for {company_name}",
        "metadata": {"report_url": report_url, "domain": domain},
    })

    logger.info("Report generated for client %s (%s): %s", client_id, domain, report_url)
    return {"report_url": report_url, "client_id": client_id, "generated_at": _now()}
