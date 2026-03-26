"""
CRM Reports Router
Aggregation reports powered by Supabase service role queries.
All endpoints require server-side execution — cannot be done safely from the frontend.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from backend.services.supabase_crm import supabase_available, get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/reports", tags=["crm-reports"])

MONTH_YEAR_RE = re.compile(r"^\d{4}-\d{2}$")


def _validate_month_year(month_year: str) -> None:
    if not MONTH_YEAR_RE.match(month_year):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month_year must be in format YYYY-MM",
        )


def _month_year() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _month_range(month_year: str) -> tuple[str, str]:
    year, month = (int(x) for x in month_year.split("-"))
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return (
        f"{year:04d}-{month:02d}-01T00:00:00+00:00",
        f"{next_year:04d}-{next_month:02d}-01T00:00:00+00:00",
    )


# ─── Pipeline Report ──────────────────────────────────────────────────────────

@router.get("/pipeline")
async def pipeline_report(
    rep_id: Optional[str] = None,
    team_lead_id: Optional[str] = None,
):
    """
    Pipeline health report.
    Returns stage distribution, win rate, lost-reason breakdown.
    """
    if not supabase_available():
        return _empty_pipeline()

    try:
        sb = get_supabase()
        query = sb.table("prospects").select("stage, lost_reason, last_activity_at, created_at")

        if rep_id:
            query = query.eq("assigned_rep_id", rep_id)
        # team_lead_id filter requires a join — omit for now, apply via RLS

        res = query.execute()
        rows = res.data or []

        stage_dist: dict = defaultdict(int)
        lost_reasons: dict = defaultdict(int)
        closed_won = 0
        total_active = 0

        for row in rows:
            stage = row.get("stage", "new")
            stage_dist[stage] += 1
            if stage == "lost" and row.get("lost_reason"):
                lost_reasons[row["lost_reason"]] += 1
            if stage == "closed_won":
                closed_won += 1
            if stage not in ("closed_won", "lost"):
                total_active += 1

        total_closed = closed_won + stage_dist.get("lost", 0)
        win_rate = round(closed_won / total_closed * 100, 1) if total_closed > 0 else 0.0

        return {
            "stage_distribution": dict(stage_dist),
            "avg_days_in_stage": {},  # Requires created_at per stage — future enhancement
            "bottleneck_stage": _find_bottleneck(stage_dist),
            "win_rate": win_rate,
            "lost_reason_breakdown": [
                {"reason": k, "count": v} for k, v in sorted(lost_reasons.items(), key=lambda x: -x[1])
            ],
            "total_prospects": len(rows),
            "active_in_pipeline": total_active,
        }
    except Exception as exc:
        logger.error("pipeline_report error: %s", exc)
        return _empty_pipeline()


def _find_bottleneck(stage_dist: dict) -> Optional[str]:
    """Return the stage with the most prospects (excluding terminal stages)."""
    active_stages = {
        k: v for k, v in stage_dist.items()
        if k not in ("closed_won", "lost", "new")
    }
    if not active_stages:
        return None
    return max(active_stages, key=lambda k: active_stages[k])


def _empty_pipeline() -> dict:
    return {
        "stage_distribution": {},
        "avg_days_in_stage": {},
        "bottleneck_stage": None,
        "win_rate": 0.0,
        "lost_reason_breakdown": [],
        "total_prospects": 0,
        "active_in_pipeline": 0,
    }


# ─── Commission Report ────────────────────────────────────────────────────────

@router.get("/commissions")
async def commission_report(month_year: str):
    """
    Commission report for a given month.
    Returns per-rep breakdown: closing, residual, overrides, clawbacks, total.
    """
    _validate_month_year(month_year)
    if not supabase_available():
        return {"month_year": month_year, "total_payout": 0.0, "by_rep": [], "clawbacks": []}

    try:
        sb = get_supabase()
        res = (
            sb.table("commissions")
            .select("*, rep:rep_id(id, full_name, email, role)")
            .eq("month_year", month_year)
            .execute()
        )
        rows = res.data or []

        by_rep: dict = defaultdict(lambda: {
            "closing": 0.0, "residual": 0.0, "override": 0.0,
            "residual_override": 0.0, "clawback": 0.0, "total": 0.0,
        })
        rep_meta: dict = {}
        clawbacks = []

        for row in rows:
            rep = row.get("rep") or {}
            rep_id = row.get("rep_id", "")
            rep_meta[rep_id] = rep
            commission_type = row.get("type", "")
            amount = float(row.get("amount") or 0)

            if commission_type == "clawback":
                clawbacks.append({
                    "rep_id": rep_id,
                    "rep_name": rep.get("full_name", ""),
                    "client_id": row.get("client_id"),
                    "amount": amount,
                })
                by_rep[rep_id]["clawback"] += amount
            else:
                by_rep[rep_id][commission_type] = by_rep[rep_id].get(commission_type, 0.0) + amount

            by_rep[rep_id]["total"] += amount

        total_payout = sum(v["total"] for v in by_rep.values())

        return {
            "month_year": month_year,
            "total_payout": round(total_payout, 2),
            "by_rep": [
                {
                    "rep_id": rep_id,
                    "rep_name": rep_meta.get(rep_id, {}).get("full_name", ""),
                    "rep_email": rep_meta.get(rep_id, {}).get("email", ""),
                    "rep_role": rep_meta.get(rep_id, {}).get("role", ""),
                    **{k: round(v, 2) for k, v in data.items()},
                }
                for rep_id, data in sorted(by_rep.items())
            ],
            "clawbacks": clawbacks,
        }
    except Exception as exc:
        logger.error("commission_report error: %s", exc)
        return {"month_year": month_year, "total_payout": 0.0, "by_rep": [], "clawbacks": []}


# ─── Charlotte Report ─────────────────────────────────────────────────────────

@router.get("/charlotte")
async def charlotte_report(
    month_year: Optional[str] = None,
    sequence_id: Optional[str] = None,
):
    """
    Charlotte email campaign report.
    Returns send/open/click/reply rates, positive-reply funnel, closes attributed.
    """
    if month_year:
        _validate_month_year(month_year)
    if not supabase_available():
        return _empty_charlotte(month_year)

    try:
        sb = get_supabase()
        target_month = month_year or _month_year()
        start, end = _month_range(target_month)

        sent_res = (
            sb.table("email_events")
            .select("id", count="exact")
            .gte("sent_at", start).lt("sent_at", end)
            .execute()
        )
        opened_res = (
            sb.table("email_events")
            .select("id", count="exact")
            .gte("opened_at", start).lt("opened_at", end)
            .execute()
        )
        clicked_res = (
            sb.table("email_events")
            .select("id", count="exact")
            .gte("clicked_at", start).lt("clicked_at", end)
            .execute()
        )
        replied_res = (
            sb.table("email_events")
            .select("id", count="exact")
            .gte("replied_at", start).lt("replied_at", end)
            .execute()
        )
        positive_res = (
            sb.table("email_events")
            .select("id", count="exact")
            .gte("replied_at", start).lt("replied_at", end)
            .eq("reply_sentiment", "positive")
            .execute()
        )
        closes_res = (
            sb.table("clients")
            .select("id", count="exact")
            .gte("close_date", start).lt("close_date", end)
            .eq("source", "charlotte")
            .execute()
        )

        sent = sent_res.count or 0
        opened = opened_res.count or 0
        clicked = clicked_res.count or 0
        replied = replied_res.count or 0
        positive = positive_res.count or 0
        closes = closes_res.count or 0

        return {
            "month_year": target_month,
            "emails_sent": sent,
            "open_rate": round(opened / sent * 100, 1) if sent else 0.0,
            "click_rate": round(clicked / sent * 100, 1) if sent else 0.0,
            "reply_rate": round(replied / sent * 100, 1) if sent else 0.0,
            "positive_reply_rate": round(positive / replied * 100, 1) if replied else 0.0,
            "closes_attributed": closes,
            "sequences": [],
        }
    except Exception as exc:
        logger.error("charlotte_report error: %s", exc)
        return _empty_charlotte(month_year)


def _empty_charlotte(month_year: Optional[str]) -> dict:
    return {
        "month_year": month_year,
        "emails_sent": 0,
        "open_rate": 0.0,
        "click_rate": 0.0,
        "reply_rate": 0.0,
        "positive_reply_rate": 0.0,
        "closes_attributed": 0,
        "sequences": [],
    }


# ─── Client Health Report ─────────────────────────────────────────────────────

@router.get("/client-health")
async def client_health_report():
    """
    Client health report.
    Returns churn risk distribution, MRR totals, upsell opportunities.
    """
    if not supabase_available():
        return _empty_client_health()

    try:
        sb = get_supabase()
        res = sb.table("clients").select("id, status, mrr, churn_risk_score, nps_latest, plan").execute()
        clients = res.data or []

        total = len(clients)
        active = sum(1 for c in clients if c.get("status") == "active")
        past_due = sum(1 for c in clients if c.get("status") == "past_due")

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        churned_mtd_res = (
            sb.table("clients")
            .select("id", count="exact")
            .eq("status", "churned")
            .gte("updated_at", month_start)
            .execute()
        )
        churned_mtd = churned_mtd_res.count or 0

        mrr_total = sum(c.get("mrr") or 0 for c in clients if c.get("status") == "active")
        mrr_at_risk = sum(
            c.get("mrr") or 0 for c in clients
            if c.get("status") == "active" and c.get("churn_risk_score") in ("medium", "high")
        )

        risk_dist = defaultdict(int)
        for c in clients:
            if c.get("status") == "active":
                risk_dist[c.get("churn_risk_score", "low")] += 1

        nps_scores = [c.get("nps_latest") for c in clients if c.get("nps_latest") is not None]
        avg_nps = round(sum(nps_scores) / len(nps_scores), 1) if nps_scores else None

        upsell_opps = sum(
            1 for c in clients
            if c.get("status") == "active"
            and c.get("plan") in ("starter", "shield")
            and c.get("churn_risk_score") == "low"
        )

        return {
            "total_clients": total,
            "active": active,
            "past_due": past_due,
            "churned_mtd": churned_mtd,
            "mrr_total": round(mrr_total, 2),
            "mrr_at_risk": round(mrr_at_risk, 2),
            "churn_risk_distribution": {
                "low": risk_dist["low"],
                "medium": risk_dist["medium"],
                "high": risk_dist["high"],
            },
            "avg_nps": avg_nps,
            "upsell_opportunities": upsell_opps,
        }
    except Exception as exc:
        logger.error("client_health_report error: %s", exc)
        return _empty_client_health()


def _empty_client_health() -> dict:
    return {
        "total_clients": 0,
        "active": 0,
        "past_due": 0,
        "churned_mtd": 0,
        "mrr_total": 0.0,
        "mrr_at_risk": 0.0,
        "churn_risk_distribution": {"low": 0, "medium": 0, "high": 0},
        "avg_nps": None,
        "upsell_opportunities": 0,
    }


# ─── Rep Performance Report ───────────────────────────────────────────────────

@router.get("/rep-performance")
async def rep_performance_report(
    month_year: Optional[str] = None,
    team_lead_id: Optional[str] = None,
):
    """
    Per-rep performance report — daily non-negotiable completion, closes, MRR, ranking.
    """
    if month_year:
        _validate_month_year(month_year)
    if not supabase_available():
        return {"month_year": month_year, "reps": []}

    target_month = month_year or _month_year()
    start, end = _month_range(target_month)

    try:
        sb = get_supabase()

        # Load reps
        rep_query = sb.table("users").select("id, full_name, email, role, team_lead_id, daily_call_target, daily_loom_target, daily_scan_target").eq("role", "rep").eq("status", "active")
        if team_lead_id:
            rep_query = rep_query.eq("team_lead_id", team_lead_id)
        reps_res = rep_query.execute()
        reps = reps_res.data or []

        if not reps:
            return {"month_year": target_month, "reps": []}

        rep_ids = [r["id"] for r in reps]

        # Bulk load activities for the month
        acts_res = (
            sb.table("activities")
            .select("created_by, type")
            .in_("created_by", rep_ids)
            .gte("created_at", start)
            .lt("created_at", end)
            .execute()
        )
        # Count activities by rep and type
        act_counts: dict = defaultdict(lambda: defaultdict(int))
        for act in (acts_res.data or []):
            act_counts[act["created_by"]][act["type"]] += 1

        # Bulk load closes for the month
        closes_res = (
            sb.table("clients")
            .select("closing_rep_id, mrr")
            .in_("closing_rep_id", rep_ids)
            .gte("close_date", start)
            .lt("close_date", end)
            .execute()
        )
        rep_closes: dict = defaultdict(list)
        for c in (closes_res.data or []):
            rep_closes[c["closing_rep_id"]].append(c.get("mrr") or 0)

        # Bulk load commissions for the month
        comm_res = (
            sb.table("commissions")
            .select("rep_id, amount")
            .in_("rep_id", rep_ids)
            .eq("month_year", target_month)
            .execute()
        )
        rep_commissions: dict = defaultdict(float)
        for c in (comm_res.data or []):
            rep_commissions[c["rep_id"]] += float(c.get("amount") or 0)

        result_reps = []
        for rep in reps:
            rep_id = rep["id"]
            counts = act_counts[rep_id]
            closes = rep_closes[rep_id]
            mrr_closed = sum(closes)
            commission = rep_commissions[rep_id]

            result_reps.append({
                "rep_id": rep_id,
                "rep_name": rep.get("full_name", ""),
                "rep_email": rep.get("email", ""),
                "calls_made": counts["call"],
                "looms_sent": counts.get("loom_sent", 0),
                "scans_run": counts["scan_run"],
                "closes": len(closes),
                "mrr_closed": round(mrr_closed, 2),
                "commission_earned": round(commission, 2),
                "daily_call_target": rep.get("daily_call_target", 30),
                "daily_loom_target": rep.get("daily_loom_target", 5),
                "daily_scan_target": rep.get("daily_scan_target", 10),
            })

        # Rank by mrr_closed descending
        result_reps.sort(key=lambda r: r["mrr_closed"], reverse=True)
        for i, r in enumerate(result_reps):
            r["rank"] = i + 1

        return {"month_year": target_month, "reps": result_reps}

    except Exception as exc:
        logger.error("rep_performance_report error: %s", exc)
        return {"month_year": month_year, "reps": []}


# ─── Forecast Report ──────────────────────────────────────────────────────────

@router.get("/forecast")
async def forecast_report(months_ahead: int = 3):
    """
    Revenue forecast for next N months.
    Uses current MRR, pipeline value × assumed 20% close rate, 5% monthly churn.
    """
    if not 1 <= months_ahead <= 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="months_ahead must be between 1 and 12",
        )
    if not supabase_available():
        return {"months_ahead": months_ahead, "current_mrr": 0.0, "projected_mrr": []}

    try:
        sb = get_supabase()

        # Current MRR
        clients_res = sb.table("clients").select("mrr").eq("status", "active").execute()
        current_mrr = sum(c.get("mrr") or 0 for c in (clients_res.data or []))

        # Pipeline value (closed_won excluded, all active stages)
        pipeline_res = (
            sb.table("prospects")
            .select("stage")
            .not_.in_("stage", ["closed_won", "lost"])
            .execute()
        )
        pipeline_count = len(pipeline_res.data or [])

        # Assumed average MRR per deal = current_mrr / active clients or $150 fallback
        active_count = len(clients_res.data or []) or 1
        avg_deal_mrr = current_mrr / active_count if current_mrr else 150
        pipeline_value = pipeline_count * avg_deal_mrr

        assumed_close_rate = 0.20
        assumed_churn_rate = 0.05

        projected = []
        running_mrr = current_mrr
        for i in range(months_ahead):
            new_mrr = pipeline_value * assumed_close_rate / months_ahead
            churn_mrr = running_mrr * assumed_churn_rate
            running_mrr = running_mrr + new_mrr - churn_mrr
            now = datetime.now(timezone.utc)
            month = (now.month + i) % 12 or 12
            year = now.year + (now.month + i - 1) // 12
            projected.append({
                "month": f"{year:04d}-{month:02d}",
                "projected_mrr": round(running_mrr, 2),
                "new_mrr": round(new_mrr, 2),
                "churn_mrr": round(churn_mrr, 2),
            })

        return {
            "months_ahead": months_ahead,
            "current_mrr": round(current_mrr, 2),
            "projected_mrr": projected,
            "pipeline_value": round(pipeline_value, 2),
            "assumed_close_rate": assumed_close_rate,
            "assumed_churn_rate": assumed_churn_rate,
        }
    except Exception as exc:
        logger.error("forecast_report error: %s", exc)
        return {
            "months_ahead": months_ahead,
            "current_mrr": 0.0,
            "projected_mrr": [],
            "pipeline_value": 0.0,
            "assumed_close_rate": 0.20,
            "assumed_churn_rate": 0.05,
        }


# ─── Attribution Report ───────────────────────────────────────────────────────

@router.get("/attribution")
async def attribution_report(month_year: Optional[str] = None):
    """
    Revenue attribution by prospect source for a given month.
    """
    if month_year:
        _validate_month_year(month_year)
    if not supabase_available():
        return _empty_attribution(month_year)

    target_month = month_year or _month_year()
    start, end = _month_range(target_month)

    try:
        sb = get_supabase()
        # Join clients with their originating prospects to get source
        res = (
            sb.table("clients")
            .select("id, mrr, prospect:prospect_id(source)")
            .gte("close_date", start)
            .lt("close_date", end)
            .execute()
        )
        rows = res.data or []

        by_source: dict = defaultdict(lambda: {"closes": 0, "mrr": 0.0})
        for row in rows:
            source = (row.get("prospect") or {}).get("source", "other")
            normalized = _normalize_source(source)
            by_source[normalized]["closes"] += 1
            by_source[normalized]["mrr"] += float(row.get("mrr") or 0)

        total_closes = sum(v["closes"] for v in by_source.values())
        total_mrr = sum(v["mrr"] for v in by_source.values())

        return {
            "month_year": target_month,
            "total_closes": total_closes,
            "total_mrr": round(total_mrr, 2),
            "by_source": {
                k: {"closes": v["closes"], "mrr": round(v["mrr"], 2)}
                for k, v in by_source.items()
            },
        }
    except Exception as exc:
        logger.error("attribution_report error: %s", exc)
        return _empty_attribution(month_year)


def _normalize_source(source: str) -> str:
    if source in ("charlotte", "outbound"):
        return "charlotte_outbound"
    if source in ("inbound", "website", "referral_partner"):
        return "inbound"
    if source == "referral":
        return "referral"
    return "other"


def _empty_attribution(month_year: Optional[str]) -> dict:
    return {
        "month_year": month_year,
        "total_closes": 0,
        "total_mrr": 0.0,
        "by_source": {
            "charlotte_outbound": {"closes": 0, "mrr": 0.0},
            "inbound": {"closes": 0, "mrr": 0.0},
            "referral": {"closes": 0, "mrr": 0.0},
            "other": {"closes": 0, "mrr": 0.0},
        },
    }
