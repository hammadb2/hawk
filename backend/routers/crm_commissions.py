"""
CRM Commissions Router
Month-end commission calculation and CSV export for Deel payroll.
All operations use service role — complex multi-table business logic.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services.supabase_crm import (
    supabase_available,
    get_supabase,
    insert_commission,
    write_audit_log,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/commissions", tags=["crm-commissions"])

COMMISSION_RATES = {
    "rep_closing": 0.30,
    "rep_residual": 0.10,
    "tl_personal": 0.20,        # TL closing their own deal
    "tl_override": 0.05,        # TL override on rep closes
    "tl_residual_override": 0.03,
    "hos_override": 0.03,
    "hos_residual_override": 0.02,
}


def _month_range(month_year: str) -> tuple[str, str]:
    """Return ISO start/end for a YYYY-MM month."""
    year, month = (int(x) for x in month_year.split("-"))
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return (
        f"{year:04d}-{month:02d}-01T00:00:00+00:00",
        f"{next_year:04d}-{next_month:02d}-01T00:00:00+00:00",
    )


# ─── Models ───────────────────────────────────────────────────────────────────

class CalculateRequest(BaseModel):
    month_year: str  # format: "2026-03"


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/calculate")
async def calculate_commissions(body: CalculateRequest):
    """
    Trigger month-end commission recalculation.
    Computes:
      1. Residual commissions — 10% of MRR per active client per closing rep
      2. TL residual overrides — 3% of MRR for clients closed by team members
      3. HoS residual overrides — 2% of MRR for all active clients
    Closing commissions are written at close-time by the close_won endpoint.
    This endpoint handles recurring residuals and override layers.
    """
    if not re.match(r"^\d{4}-\d{2}$", body.month_year):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month_year must be in format YYYY-MM",
        )
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()
    month_year = body.month_year
    inserted = 0

    try:
        # ── Active clients ───────────────────────────────────────────────────
        clients_res = (
            sb.table("clients")
            .select("id, mrr, closing_rep_id, status")
            .eq("status", "active")
            .execute()
        )
        clients = clients_res.data or []

        # ── Load all reps to build TL maps ───────────────────────────────────
        reps_res = sb.table("users").select("id, role, team_lead_id").execute()
        users = {u["id"]: u for u in (reps_res.data or [])}

        # Find HoS (there may be one or more)
        hos_ids = [u["id"] for u in users.values() if u.get("role") == "hos"]

        # ── Purge existing residuals for this month (avoid double-calc) ──────
        sb.table("commissions").delete().eq("month_year", month_year).in_(
            "type", ["residual", "residual_override"]
        ).execute()

        # ── Calculate per-client residuals ───────────────────────────────────
        for client in clients:
            mrr = client.get("mrr") or 0
            if mrr <= 0:
                continue
            closing_rep_id = client.get("closing_rep_id")
            client_id = client["id"]

            # Rep residual (10%)
            if closing_rep_id:
                rep_residual = round(mrr * COMMISSION_RATES["rep_residual"], 2)
                insert_commission({
                    "rep_id": closing_rep_id,
                    "type": "residual",
                    "amount": rep_residual,
                    "client_id": client_id,
                    "month_year": month_year,
                    "status": "pending",
                })
                inserted += 1

                # TL residual override (3%) on rep's clients
                rep = users.get(closing_rep_id, {})
                team_lead_id = rep.get("team_lead_id")
                if team_lead_id and rep.get("role") == "rep":
                    tl_residual = round(mrr * COMMISSION_RATES["tl_residual_override"], 2)
                    insert_commission({
                        "rep_id": team_lead_id,
                        "type": "residual_override",
                        "amount": tl_residual,
                        "client_id": client_id,
                        "month_year": month_year,
                        "status": "pending",
                    })
                    inserted += 1

            # HoS residual override (2%) on all active clients
            for hos_id in hos_ids:
                hos_residual = round(mrr * COMMISSION_RATES["hos_residual_override"], 2)
                insert_commission({
                    "rep_id": hos_id,
                    "type": "residual_override",
                    "amount": hos_residual,
                    "client_id": client_id,
                    "month_year": month_year,
                    "status": "pending",
                })
                inserted += 1

        write_audit_log({
            "action": "commissions_calculated",
            "record_type": "commission",
            "record_id": month_year,
            "new_value": {"month_year": month_year, "records_created": inserted},
        })
        logger.info("Commission calculation complete for %s: %d records", month_year, inserted)

        return {"calculated": inserted, "month_year": month_year}

    except Exception as exc:
        logger.error("Commission calculation failed for %s: %s", month_year, exc)
        raise HTTPException(status_code=500, detail=f"Calculation failed: {exc}") from exc


@router.get("/export")
async def export_commissions_csv(month_year: str):
    """
    Export commission data as CSV for Deel payroll processing.
    Returns a streaming CSV response with all commissions for the month.
    """
    if not re.match(r"^\d{4}-\d{2}$", month_year):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month_year must be in format YYYY-MM",
        )
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    sb = get_supabase()

    try:
        # Load commissions with rep details
        res = (
            sb.table("commissions")
            .select("*, rep:rep_id(id, full_name, email, role)")
            .eq("month_year", month_year)
            .order("rep_id")
            .order("type")
            .execute()
        )
        rows = res.data or []

        # Build CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "rep_id", "rep_name", "rep_email", "rep_role",
            "commission_type", "client_id", "amount",
            "month_year", "status",
        ])
        for row in rows:
            rep = row.get("rep") or {}
            writer.writerow([
                row.get("rep_id", ""),
                rep.get("full_name", ""),
                rep.get("email", ""),
                rep.get("role", ""),
                row.get("type", ""),
                row.get("client_id", ""),
                row.get("amount", 0),
                row.get("month_year", ""),
                row.get("status", ""),
            ])

        output.seek(0)
        filename = f"hawk-commissions-{month_year}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as exc:
        logger.error("Commission CSV export failed for %s: %s", month_year, exc)
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
