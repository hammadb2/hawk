"""ARIA Phase 6 — Chart data service for inline visual outputs.

Provides structured data for Recharts-rendered charts inside ARIA chat:
- compare_periods: side-by-side metric comparison (bar chart)
- revenue_trend: MRR over time (area chart)
- pipeline_funnel: prospect stages (funnel/bar chart)
- campaign_health: email engagement metrics (bar chart)
- va_leaderboard: VA performance ranking (horizontal bar chart)
- client_health_distribution: health score histogram (bar chart)
"""

from __future__ import annotations

import json
import logging
import os
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


# ── Helpers ──────────────────────────────────────────────────────────────


def _count_rows(table: str, filters: dict[str, str]) -> int:
    """Get exact count from a PostgREST table with filters."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb(), "Prefer": "count=exact"},
        params={**filters, "select": "id", "limit": "0"},
        timeout=15.0,
    )
    cr = r.headers.get("content-range", "")
    if "/" in cr:
        try:
            return int(cr.split("/")[1])
        except (ValueError, IndexError):
            pass
    return 0


def _fetch_rows(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch rows from a PostgREST table."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_sb(),
        params=params,
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.warning("Chart data fetch failed for %s: %s", table, r.text[:200])
        return []
    return r.json() or []


# ── Chart: Pipeline Funnel ───────────────────────────────────────────────


def get_pipeline_funnel() -> dict[str, Any]:
    """Prospect count by pipeline stage — rendered as a horizontal bar / funnel chart."""
    stages = [
        ("new", "New"),
        ("scanned", "Scanned"),
        ("loom_sent", "Loom Sent"),
        ("replied", "Replied"),
        ("call_booked", "Call Booked"),
        ("proposal_sent", "Proposal"),
        ("closed_won", "Won"),
        ("lost", "Lost"),
    ]
    data = []
    for stage_key, stage_label in stages:
        count = _count_rows("prospects", {"stage": f"eq.{stage_key}"})
        data.append({"stage": stage_label, "count": count})

    return {
        "chart_type": "pipeline_funnel",
        "title": "Pipeline Funnel",
        "data": data,
        "x_key": "stage",
        "y_keys": ["count"],
        "colors": ["#10b981"],
    }


# ── Chart: Revenue Trend ────────────────────────────────────────────────


def get_revenue_trend(months: int = 6) -> dict[str, Any]:
    """MRR trend over the last N months based on client data."""
    # Fetch all active clients with plan and MRR
    clients = _fetch_rows("clients", {
        "status": "eq.active",
        "select": "id,plan,mrr_cents,created_at",
        "limit": "1000",
    })

    # Build monthly MRR: count clients created before each month-end
    now = datetime.now(timezone.utc)
    data = []
    for i in range(months - 1, -1, -1):
        # Calculate month offset using calendar arithmetic
        target_month = now.month - i
        target_year = now.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        month_date = now.replace(year=target_year, month=target_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_label = month_date.strftime("%b %Y")

        # Sum MRR for clients created before this month-end
        mrr = 0
        count = 0
        for c in clients:
            created = c.get("created_at", "")
            if created and created < month_end.isoformat():
                mrr += c.get("mrr_cents") or 0
                count += 1

        data.append({
            "month": month_label,
            "mrr": round(mrr / 100, 2),
            "clients": count,
        })

    return {
        "chart_type": "revenue_trend",
        "title": "MRR Trend",
        "data": data,
        "x_key": "month",
        "y_keys": ["mrr"],
        "colors": ["#6366f1"],
        "y_label": "MRR ($)",
    }


# ── Chart: Compare Periods ──────────────────────────────────────────────


def compare_periods(metric: str, period1: str, period2: str) -> dict[str, Any]:
    """Compare a metric across two time periods.

    Supported metrics: calls_booked, emails_sent, prospects_added, revenue
    Periods: "this_week", "last_week", "this_month", "last_month"
    """
    now = datetime.now(timezone.utc)

    def _period_range(period: str) -> tuple[str, str]:
        if period == "this_week":
            start = now - timedelta(days=now.weekday())
            return start.replace(hour=0, minute=0, second=0).isoformat(), now.isoformat()
        elif period == "last_week":
            end = now - timedelta(days=now.weekday())
            start = end - timedelta(days=7)
            return start.replace(hour=0, minute=0, second=0).isoformat(), end.replace(hour=0, minute=0, second=0).isoformat()
        elif period == "this_month":
            start = now.replace(day=1, hour=0, minute=0, second=0)
            return start.isoformat(), now.isoformat()
        elif period == "last_month":
            first_this = now.replace(day=1, hour=0, minute=0, second=0)
            end = first_this - timedelta(seconds=1)
            start = end.replace(day=1, hour=0, minute=0, second=0)
            return start.isoformat(), first_this.isoformat()
        else:
            # Default to last 7 days
            return (now - timedelta(days=7)).isoformat(), now.isoformat()

    r1_start, r1_end = _period_range(period1)
    r2_start, r2_end = _period_range(period2)

    def _count_metric(start: str, end: str) -> int:
        date_filter = f"(created_at.gte.{start},created_at.lte.{end})"
        if metric == "calls_booked":
            return _count_rows("activities", {
                "type": "eq.call_booked",
                "and": date_filter,
            })
        elif metric == "emails_sent":
            return _count_rows("activities", {
                "type": "eq.email_sent",
                "and": date_filter,
            })
        elif metric == "prospects_added":
            return _count_rows("prospects", {
                "and": date_filter,
            })
        elif metric == "revenue":
            clients = _fetch_rows("clients", {
                "status": "eq.active",
                "created_at": f"lte.{end}",
                "select": "mrr_cents",
                "limit": "500",
            })
            return sum(c.get("mrr_cents") or 0 for c in clients) // 100
        return 0

    v1 = _count_metric(r1_start, r1_end)
    v2 = _count_metric(r2_start, r2_end)

    label1 = period1.replace("_", " ").title()
    label2 = period2.replace("_", " ").title()

    data = [
        {"period": label1, "value": v1},
        {"period": label2, "value": v2},
    ]

    change = 0.0
    if v1 > 0:
        change = round(((v2 - v1) / v1) * 100, 1)

    return {
        "chart_type": "compare_periods",
        "title": f"{metric.replace('_', ' ').title()}: {label1} vs {label2}",
        "data": data,
        "x_key": "period",
        "y_keys": ["value"],
        "colors": ["#6366f1", "#10b981"],
        "change_pct": change,
    }


# ── Chart: Campaign Health ───────────────────────────────────────────────


def get_campaign_health() -> dict[str, Any]:
    """Email engagement metrics from activities — open rate, click rate, reply rate."""
    # Count different activity types as engagement proxies
    total_sent = _count_rows("activities", {"type": "eq.email_sent"})
    total_opened = _count_rows("activities", {"type": "eq.email_opened"})
    total_clicked = _count_rows("activities", {"type": "eq.email_clicked"})
    total_replied = _count_rows("activities", {"type": "eq.email_replied"})
    total_bounced = _count_rows("activities", {"type": "eq.email_bounced"})

    data = [
        {"metric": "Sent", "count": total_sent},
        {"metric": "Opened", "count": total_opened},
        {"metric": "Clicked", "count": total_clicked},
        {"metric": "Replied", "count": total_replied},
        {"metric": "Bounced", "count": total_bounced},
    ]

    rates: dict[str, float] = {}
    if total_sent > 0:
        rates["open_rate"] = round((total_opened / total_sent) * 100, 1)
        rates["click_rate"] = round((total_clicked / total_sent) * 100, 1)
        rates["reply_rate"] = round((total_replied / total_sent) * 100, 1)
        rates["bounce_rate"] = round((total_bounced / total_sent) * 100, 1)

    return {
        "chart_type": "campaign_health",
        "title": "Campaign Health",
        "data": data,
        "x_key": "metric",
        "y_keys": ["count"],
        "colors": ["#3b82f6"],
        "rates": rates,
    }


# ── Chart: VA Leaderboard ───────────────────────────────────────────────


def get_va_leaderboard() -> dict[str, Any]:
    """VA performance ranking by health score — horizontal bar chart."""
    vas = _fetch_rows("profiles", {
        "role_type": "eq.va_outreach",
        "status": "eq.active",
        "select": "id,full_name,health_score",
        "order": "health_score.desc.nullslast",
        "limit": "20",
    })

    data = []
    for va in vas:
        name = va.get("full_name") or "Unknown"
        # Shorten name for chart display
        parts = name.split()
        short = f"{parts[0]} {parts[1][0]}." if len(parts) > 1 else name
        data.append({
            "name": short,
            "score": va.get("health_score") or 0,
        })

    return {
        "chart_type": "va_leaderboard",
        "title": "VA Performance Leaderboard",
        "data": data,
        "x_key": "name",
        "y_keys": ["score"],
        "colors": ["#f59e0b"],
    }


# ── Chart: Client Health Distribution ────────────────────────────────────


def get_client_health_distribution() -> dict[str, Any]:
    """Distribution of client health scores — histogram/bar chart."""
    scores = _fetch_rows("aria_client_health_scores", {
        "select": "score,at_risk",
        "limit": "500",
    })

    buckets = {
        "0-20": 0,
        "21-40": 0,
        "41-60": 0,
        "61-80": 0,
        "81-100": 0,
    }
    at_risk_count = 0

    for s in scores:
        score = s.get("score", 0) or 0
        if s.get("at_risk"):
            at_risk_count += 1
        if score <= 20:
            buckets["0-20"] += 1
        elif score <= 40:
            buckets["21-40"] += 1
        elif score <= 60:
            buckets["41-60"] += 1
        elif score <= 80:
            buckets["61-80"] += 1
        else:
            buckets["81-100"] += 1

    data = [{"range": k, "count": v} for k, v in buckets.items()]

    return {
        "chart_type": "client_health_distribution",
        "title": "Client Health Score Distribution",
        "data": data,
        "x_key": "range",
        "y_keys": ["count"],
        "colors": ["#10b981", "#10b981", "#f59e0b", "#ef4444", "#ef4444"],
        "at_risk_count": at_risk_count,
        "total": len(scores),
    }


# ── Function execution dispatcher ────────────────────────────────────────


def execute_chart_function(name: str, args: dict[str, Any]) -> str:
    """Execute a chart function and return JSON result."""
    try:
        if name == "get_pipeline_funnel_chart":
            return json.dumps(get_pipeline_funnel())
        elif name == "get_revenue_trend_chart":
            months = args.get("months", 6)
            return json.dumps(get_revenue_trend(months=months))
        elif name == "compare_periods_chart":
            return json.dumps(compare_periods(
                metric=args.get("metric", "prospects_added"),
                period1=args.get("period1", "last_week"),
                period2=args.get("period2", "this_week"),
            ))
        elif name == "get_campaign_health_chart":
            return json.dumps(get_campaign_health())
        elif name == "get_va_leaderboard_chart":
            return json.dumps(get_va_leaderboard())
        elif name == "get_client_health_chart":
            return json.dumps(get_client_health_distribution())
        else:
            return json.dumps({"error": f"Unknown chart function: {name}"})
    except Exception as exc:
        logger.exception("Chart function execution failed: %s", exc)
        return json.dumps({"error": str(exc)})


# ── OpenAI function definitions for charts ───────────────────────────────

CHART_FUNCTION_DEFINITIONS = [
    {
        "name": "get_pipeline_funnel_chart",
        "description": "Get a visual pipeline funnel chart showing prospect counts by stage. Returns chart data rendered as an interactive funnel visualization in the chat.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_revenue_trend_chart",
        "description": "Get a visual MRR trend chart showing monthly recurring revenue over time. Returns chart data rendered as an area chart in the chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "Number of months to show (default 6)",
                },
            },
        },
    },
    {
        "name": "compare_periods_chart",
        "description": "Compare a metric across two time periods with a visual bar chart. Useful for week-over-week or month-over-month comparisons.",
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["calls_booked", "emails_sent", "prospects_added", "revenue"],
                    "description": "The metric to compare",
                },
                "period1": {
                    "type": "string",
                    "enum": ["this_week", "last_week", "this_month", "last_month"],
                    "description": "First time period",
                },
                "period2": {
                    "type": "string",
                    "enum": ["this_week", "last_week", "this_month", "last_month"],
                    "description": "Second time period",
                },
            },
            "required": ["metric", "period1", "period2"],
        },
    },
    {
        "name": "get_campaign_health_chart",
        "description": "Get a visual chart of email campaign health showing sent, opened, clicked, replied, and bounced counts with engagement rates.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_va_leaderboard_chart",
        "description": "Get a visual leaderboard chart ranking VAs by performance score. Returns a horizontal bar chart.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_client_health_chart",
        "description": "Get a visual distribution chart of client health scores showing how many clients fall in each score range.",
        "parameters": {"type": "object", "properties": {}},
    },
]
