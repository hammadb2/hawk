"""
CRM Prospects Router
Handles close-won and scan triggers — operations requiring service-role access.
Simple CRUD goes through the Supabase JS client directly (RLS enforced).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional

from backend.services.supabase_crm import (
    supabase_available,
    get_supabase,
    get_prospect_by_domain,
    update_prospect,
    log_activity,
    insert_commission,
    write_audit_log,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/prospects", tags=["crm-prospects"])

CLAWBACK_WINDOW_DAYS = 90
PLAN_MRR = {"starter": 99, "shield": 199, "enterprise": 399}
COMMISSION_RATES = {
    "rep_closing": 0.30,
    "rep_residual": 0.10,
    "tl_override": 0.05,
    "hos_override": 0.03,
}

VALID_PLANS = ["starter", "shield", "enterprise", "custom"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_year() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _get_rep_id_from_request(request: Request) -> Optional[str]:
    """Extract rep ID from Bearer JWT via Supabase auth.getUser()."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        sb = get_supabase()
        res = sb.auth.get_user(token)
        return res.user.id if res.user else None
    except Exception:
        return None


def _get_user_role(user_id: str) -> Optional[str]:
    try:
        sb = get_supabase()
        res = sb.table("users").select("role, team_lead_id").eq("id", user_id).single().execute()
        return res.data if res.data else None
    except Exception:
        return None


# ─── Close Won ────────────────────────────────────────────────────────────────

class CloseWonRequest(BaseModel):
    plan: str
    mrr: float
    payment_confirmed: bool
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


@router.post("/{prospect_id}/close")
async def close_won(prospect_id: str, body: CloseWonRequest, request: Request):
    """
    Close a deal as won.
    - Creates a Client record.
    - Calculates rep closing commission (30%).
    - Calculates TL override commission (5%) if applicable.
    - Calculates HoS override commission (3%) if applicable.
    - Moves prospect to closed_won stage.
    - Writes audit log.
    """
    if not body.payment_confirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment must be confirmed before closing a deal",
        )
    if body.mrr <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="MRR must be greater than 0",
        )
    if body.plan not in VALID_PLANS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid plan. Must be one of: {VALID_PLANS}",
        )
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()

    # Load prospect
    prospect_res = sb.table("prospects").select("*").eq("id", prospect_id).single().execute()
    if not prospect_res.data:
        raise HTTPException(status_code=404, detail="Prospect not found")
    prospect = prospect_res.data

    # Identify closing rep
    rep_id = _get_rep_id_from_request(request) or prospect.get("assigned_rep_id")

    now = _now()
    clawback_deadline = (
        datetime.now(timezone.utc) + timedelta(days=CLAWBACK_WINDOW_DAYS)
    ).isoformat()

    # Create client record
    client_data = {
        "prospect_id": prospect_id,
        "plan": body.plan,
        "mrr": body.mrr,
        "stripe_customer_id": body.stripe_customer_id,
        "stripe_subscription_id": body.stripe_subscription_id,
        "closing_rep_id": rep_id,
        "status": "active",
        "close_date": now,
        "clawback_deadline": clawback_deadline,
        "churn_risk_score": "low",
        "domain": prospect.get("domain"),
        "company_name": prospect.get("company_name"),
    }
    client_res = sb.table("clients").insert(client_data).execute()
    if not client_res.data:
        logger.error("Failed to create client for prospect %s", prospect_id)
        raise HTTPException(status_code=500, detail="Failed to create client record")

    client = client_res.data[0]
    client_id = client["id"]
    month_year = _month_year()

    # Move prospect to closed_won
    sb.table("prospects").update({
        "stage": "closed_won",
        "last_activity_at": now,
    }).eq("id", prospect_id).execute()

    # Log close_won activity
    log_activity({
        "prospect_id": prospect_id,
        "client_id": client_id,
        "type": "close_won",
        "metadata": {"plan": body.plan, "mrr": body.mrr},
    })

    # ── Closing commissions ──────────────────────────────────────────────────
    if rep_id:
        rep_user = _get_user_role(rep_id)
        rep_role = rep_user.get("role") if rep_user else "rep"
        team_lead_id = rep_user.get("team_lead_id") if rep_user else None

        closing_rate = COMMISSION_RATES["rep_closing"] if rep_role == "rep" else 0.20
        closing_commission = round(body.mrr * closing_rate, 2)
        insert_commission({
            "rep_id": rep_id,
            "type": "closing",
            "amount": closing_commission,
            "client_id": client_id,
            "month_year": month_year,
            "status": "pending",
        })
        logger.info("Closing commission $%.2f for rep %s (role: %s)", closing_commission, rep_id, rep_role)

        # TL override (5% on rep closes)
        if team_lead_id and rep_role == "rep":
            tl_commission = round(body.mrr * COMMISSION_RATES["tl_override"], 2)
            insert_commission({
                "rep_id": team_lead_id,
                "type": "override",
                "amount": tl_commission,
                "client_id": client_id,
                "month_year": month_year,
                "status": "pending",
            })
            logger.info("TL override commission $%.2f for TL %s", tl_commission, team_lead_id)

        # HoS override (3% on all closes)
        try:
            hos_res = sb.table("users").select("id").eq("role", "hos").eq("status", "active").limit(1).execute()
            if hos_res.data:
                hos_id = hos_res.data[0]["id"]
                hos_commission = round(body.mrr * COMMISSION_RATES["hos_override"], 2)
                insert_commission({
                    "rep_id": hos_id,
                    "type": "override",
                    "amount": hos_commission,
                    "client_id": client_id,
                    "month_year": month_year,
                    "status": "pending",
                })
                logger.info("HoS override commission $%.2f for HoS %s", hos_commission, hos_id)
        except Exception as exc:
            logger.error("HoS override calculation failed: %s", exc)

    write_audit_log({
        "action": "client_created",
        "record_type": "client",
        "record_id": client_id,
        "new_value": client_data,
    })

    return {**client, "prospect_id": prospect_id}


# ─── Scan ─────────────────────────────────────────────────────────────────────

@router.post("/{prospect_id}/scan")
async def run_crm_scan(prospect_id: str):
    """Trigger a HAWK security scan for the prospect's domain."""
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()

    # Load prospect
    prospect_res = sb.table("prospects").select("id, domain, company_name").eq("id", prospect_id).single().execute()
    if not prospect_res.data:
        raise HTTPException(status_code=404, detail="Prospect not found")

    domain = prospect_res.data.get("domain", "")
    if not domain:
        raise HTTPException(status_code=422, detail="Prospect has no domain set")

    # Create pending scan record
    now = _now()
    scan_insert = {
        "prospect_id": prospect_id,
        "domain": domain,
        "status": "pending",
        "created_at": now,
    }
    scan_res = sb.table("crm_scans").insert(scan_insert).execute()
    if not scan_res.data:
        raise HTTPException(status_code=500, detail="Failed to create scan record")

    scan_record = scan_res.data[0]
    scan_id = scan_record["id"]

    # Run HAWK scanner synchronously (domain-only, no auth required)
    try:
        from backend.services.scanner import run_scan as hawk_scan
        result = hawk_scan(domain, scan_id=None)

        hawk_score = result.get("score")
        findings = result.get("findings", [])
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        high = sum(1 for f in findings if f.get("severity") == "high")

        # Update scan record with results
        sb.table("crm_scans").update({
            "status": "completed",
            "hawk_score": hawk_score,
            "findings_count": len(findings),
            "critical_count": critical,
            "high_count": high,
            "findings": findings,
            "completed_at": _now(),
        }).eq("id", scan_id).execute()

        # Update prospect hawk_score
        sb.table("prospects").update({
            "hawk_score": hawk_score,
            "last_scan_at": now,
            "last_activity_at": _now(),
        }).eq("id", prospect_id).execute()

        log_activity({
            "prospect_id": prospect_id,
            "type": "scan_run",
            "metadata": {
                "scan_id": scan_id,
                "hawk_score": hawk_score,
                "findings": len(findings),
                "critical": critical,
            },
        })

        return {
            "id": scan_id,
            "prospect_id": prospect_id,
            "domain": domain,
            "hawk_score": hawk_score,
            "findings_count": len(findings),
            "critical_count": critical,
            "high_count": high,
            "status": "completed",
            "created_at": now,
        }

    except Exception as exc:
        logger.error("CRM scan failed for domain %s: %s", domain, exc)
        sb.table("crm_scans").update({
            "status": "failed",
            "error": str(exc),
        }).eq("id", scan_id).execute()

        return {
            "id": scan_id,
            "prospect_id": prospect_id,
            "domain": domain,
            "hawk_score": None,
            "findings_count": 0,
            "status": "failed",
            "error": str(exc),
            "created_at": now,
        }
