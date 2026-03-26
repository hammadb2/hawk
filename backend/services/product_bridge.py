"""
HAWK Product Bridge
Reads from the HAWK product database (SQLAlchemy) and writes sync results
into the CRM Supabase client_health_sync table.

This is the ONLY place in the codebase that queries the HAWK product DB
for CRM purposes. All reads go through here. All writes go through supabase_crm.

Architecture invariant:
  CRM frontend → Supabase (RLS)
  CRM backend  → product_bridge (SQLAlchemy read) + supabase_crm (Supabase write)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.services.churn_risk import HealthSignals, calculate as calc_churn
from backend.services.supabase_crm import get_supabase

logger = logging.getLogger(__name__)

# Features the HAWK product tracks — used to build features_accessed map
TRACKED_FEATURES = [
    "scan", "report", "domains", "compliance", "agency",
    "notifications", "hawk_ai", "breach_check",
]


# ─── Product DB reads ─────────────────────────────────────────────────────────

def get_product_user(hawk_user_id: str) -> Optional[dict]:
    """Load a HAWK product user record by ID."""
    db: Session = SessionLocal()
    try:
        from backend.models.user import User
        user = db.query(User).filter(User.id == hawk_user_id).first()
        if not user:
            return None
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "company": user.company,
            "industry": user.industry,
            "plan": user.plan,
            "trial_ends_at": user.trial_ends_at,
            "stripe_customer_id": user.stripe_customer_id,
            "stripe_subscription_id": user.stripe_subscription_id,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
    except Exception as exc:
        logger.error("get_product_user error for %s: %s", hawk_user_id, exc)
        return None
    finally:
        db.close()


def get_product_domains(hawk_user_id: str) -> list[str]:
    """Return all domains monitored by this HAWK user."""
    db: Session = SessionLocal()
    try:
        from backend.models.domain import Domain
        domains = db.query(Domain).filter(Domain.user_id == hawk_user_id).all()
        return [d.domain for d in domains]
    except Exception as exc:
        logger.error("get_product_domains error for %s: %s", hawk_user_id, exc)
        return []
    finally:
        db.close()


def get_product_scan_stats(hawk_user_id: str) -> dict:
    """Aggregate scan usage for this HAWK user."""
    db: Session = SessionLocal()
    try:
        from backend.models.scan import Scan
        from sqlalchemy import func

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        all_scans = (
            db.query(Scan)
            .filter(
                Scan.user_id == hawk_user_id,
                Scan.status == "completed",
            )
            .all()
        )

        total = len(all_scans)
        this_month = sum(
            1 for s in all_scans
            if s.completed_at and s.completed_at.replace(tzinfo=timezone.utc) >= month_start
        )

        last_scan_date = None
        completed = [s for s in all_scans if s.completed_at]
        if completed:
            latest = max(completed, key=lambda s: s.completed_at)
            last_scan_date = latest.completed_at

        return {
            "total_scans": total,
            "scans_this_month": this_month,
            "last_scan_date": last_scan_date,
        }
    except Exception as exc:
        logger.error("get_product_scan_stats error for %s: %s", hawk_user_id, exc)
        return {"total_scans": 0, "scans_this_month": 0, "last_scan_date": None}
    finally:
        db.close()


def get_product_report_stats(hawk_user_id: str) -> dict:
    """Count reports generated and downloaded."""
    db: Session = SessionLocal()
    try:
        from backend.models.report import Report
        reports = db.query(Report).filter(Report.user_id == hawk_user_id).all()
        generated = len(reports)
        downloaded = sum(1 for r in reports if getattr(r, "downloaded_at", None))
        return {"reports_generated": generated, "reports_downloaded": downloaded}
    except Exception as exc:
        logger.error("get_product_report_stats error for %s: %s", hawk_user_id, exc)
        return {"reports_generated": 0, "reports_downloaded": 0}
    finally:
        db.close()


# ─── Sync ─────────────────────────────────────────────────────────────────────

def sync_account(
    hawk_user_id: str,
    client_id: str,
    *,
    tickets_open: int = 0,
    tickets_closed_month: int = 0,
    cancellation_intent: bool = False,
    downgrade_requested: bool = False,
    upgrade_clicked: bool = False,
    payment_failed_count: int = 0,
    nps_score: Optional[int] = None,
    nps_comment: Optional[str] = None,
    nps_at: Optional[datetime] = None,
    last_login_date: Optional[datetime] = None,
    sessions_this_month: int = 0,
    avg_session_minutes: float = 0.0,
    onboarding_pct: int = 0,
    onboarding_steps_done: Optional[list] = None,
) -> dict:
    """
    Full sync for one client.
    Reads from HAWK product DB → calculates churn risk → writes to CRM Supabase.
    Returns the upserted sync record.
    """
    user = get_product_user(hawk_user_id)
    if not user:
        logger.warning("sync_account: HAWK user %s not found", hawk_user_id)
        return {}

    domains = get_product_domains(hawk_user_id)
    scan_stats = get_product_scan_stats(hawk_user_id)
    report_stats = get_product_report_stats(hawk_user_id)

    # ── Calculate churn risk ─────────────────────────────────────────────
    # Tickets open >48h — for now we use total open as a proxy
    signals = HealthSignals(
        last_login_date=last_login_date,
        scans_this_month=scan_stats["scans_this_month"],
        onboarding_pct=onboarding_pct,
        nps_score=nps_score,
        tickets_open_over_48h=min(tickets_open, 3),  # cap contribution
        payment_failed_count=payment_failed_count,
        cancellation_intent=cancellation_intent,
        downgrade_requested=downgrade_requested,
        reports_downloaded=report_stats["reports_downloaded"] > 0,
        sessions_this_month=sessions_this_month,
    )
    risk = calc_churn(signals)

    owner_name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])).strip()

    sync_payload = {
        "client_id": client_id,
        "hawk_user_id": hawk_user_id,

        # Account identity
        "account_owner_name": owner_name or None,
        "account_owner_email": user.get("email"),
        "company_name": user.get("company"),
        "plan": user.get("plan"),
        "trial_start_date": user.get("created_at").isoformat() if user.get("created_at") else None,
        "trial_end_date": user.get("trial_ends_at").isoformat() if user.get("trial_ends_at") else None,
        "billing_status": "active",  # enriched by Stripe webhooks
        "mrr": None,
        "seat_count": 1,
        "primary_domain": domains[0] if domains else None,
        "all_domains": domains,

        # Product usage
        "total_scans": scan_stats["total_scans"],
        "scans_this_month": scan_stats["scans_this_month"],
        "last_scan_date": scan_stats["last_scan_date"].isoformat() if scan_stats["last_scan_date"] else None,
        "features_accessed": {f: False for f in TRACKED_FEATURES},  # enriched from usage events
        "reports_generated": report_stats["reports_generated"],
        "reports_downloaded": report_stats["reports_downloaded"],
        "compliance_accessed": False,
        "agency_accessed": False,
        "sessions_this_month": sessions_this_month,
        "last_login_date": last_login_date.isoformat() if last_login_date else None,
        "avg_session_minutes": avg_session_minutes,
        "onboarding_pct": onboarding_pct,
        "onboarding_steps_done": onboarding_steps_done or [],

        # Health signals
        "nps_score": nps_score,
        "nps_comment": nps_comment,
        "nps_submitted_at": nps_at.isoformat() if nps_at else None,
        "tickets_open": tickets_open,
        "tickets_closed_month": tickets_closed_month,
        "cancellation_intent": cancellation_intent,
        "cancellation_intent_at": datetime.now(timezone.utc).isoformat() if cancellation_intent else None,
        "downgrade_requested": downgrade_requested,
        "upgrade_clicked": upgrade_clicked,
        "payment_failed_count": payment_failed_count,

        # Calculated
        "churn_risk_numeric": risk.numeric,
        "churn_risk_label": risk.label,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }

    # Upsert into CRM Supabase (delete old + insert, no ON CONFLICT in supabase-py yet)
    try:
        sb = get_supabase()

        # Delete existing sync record for this client
        sb.table("client_health_sync").delete().eq("client_id", client_id).execute()

        # Insert fresh record
        res = sb.table("client_health_sync").insert(sync_payload).execute()
        result = res.data[0] if res.data else sync_payload

        # Update the clients table churn risk columns
        sb.table("clients").update({
            "churn_risk_score": risk.label,
            "churn_risk_numeric": risk.numeric,
            "hawk_user_id": hawk_user_id,
        }).eq("id", client_id).execute()

        # Fire critical alert if needed
        if risk.is_critical:
            _fire_critical_churn_alert(client_id, hawk_user_id, risk.numeric, risk.signals_fired)

        logger.info(
            "Synced client %s (hawk_user: %s) — churn risk: %s (%d)",
            client_id, hawk_user_id, risk.label, risk.numeric,
        )
        return result

    except Exception as exc:
        logger.error("sync_account write to Supabase failed: %s", exc)
        return {}


def _fire_critical_churn_alert(
    client_id: str,
    hawk_user_id: str,
    score: int,
    signals: list[str],
) -> None:
    """Log a critical churn activity — WhatsApp notification handled by the notification service."""
    try:
        from backend.services.supabase_crm import get_supabase, log_activity
        sb = get_supabase()

        # Load client to get rep and CSM
        client_res = sb.table("clients").select(
            "id, closing_rep_id, csm_rep_id, company_name"
        ).eq("id", client_id).single().execute()

        if not client_res.data:
            return

        client = client_res.data
        company = client.get("company_name", "Unknown")

        log_activity({
            "client_id": client_id,
            "type": "note_added",
            "notes": f"🚨 CRITICAL churn risk ({score}/100) detected for {company}",
            "metadata": {
                "urgent": True,
                "type": "critical_churn_risk",
                "score": score,
                "signals": signals,
            },
        })

        # Attempt WhatsApp notification via charlotte service
        try:
            from backend.services.charlotte import send_whatsapp_alert
            rep_ids = list(filter(None, [
                client.get("closing_rep_id"),
                client.get("csm_rep_id"),
            ]))
            for rep_id in rep_ids:
                rep_res = sb.table("users").select("phone").eq("id", rep_id).single().execute()
                phone = (rep_res.data or {}).get("phone")
                if phone:
                    send_whatsapp_alert(
                        phone=phone,
                        message=(
                            f"🚨 CRITICAL churn risk — {company} scored {score}/100. "
                            f"Signals: {', '.join(signals[:3])}. Call them now."
                        ),
                    )
        except ImportError:
            logger.debug("charlotte.send_whatsapp_alert not available — skipping WhatsApp")
        except Exception as exc:
            logger.error("WhatsApp alert failed: %s", exc)

    except Exception as exc:
        logger.error("_fire_critical_churn_alert failed: %s", exc)
