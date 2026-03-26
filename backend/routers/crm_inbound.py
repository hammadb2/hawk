"""
CRM Inbound Router
Handles new HAWK signups and trial nurture behaviour triggers.

Routes:
  POST /api/crm/inbound/signup          — new HAWK signup (trial or paid)
  POST /api/crm/inbound/trial-event     — behaviour-triggered nurture event
  POST /api/crm/inbound/pricing-viewed  — prospect viewed pricing page
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.services.supabase_crm import (
    supabase_available,
    get_supabase,
    create_prospect,
    log_activity,
    write_audit_log,
    insert_commission,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/inbound", tags=["crm-inbound"])

INBOUND_SECRET = os.getenv("CRM_SYNC_SECRET", "")

ONBOARDING_TASKS = [
    (0,  "Welcome call",               "Reach out within 2 hours of signup to introduce yourself and the onboarding process."),
    (1,  "Onboarding email sent",       "Confirm Charlotte's automated onboarding email was delivered and opened."),
    (3,  "Onboarding check-in",         "Review onboarding checklist — if under 50% complete, book a follow-up call immediately."),
    (7,  "First week check-in call",    "Review first scan results together. Answer questions. Confirm they're getting value."),
    (14, "Health check call",           "Review scan history and findings. Surface upsell if on Starter plan."),
    (30, "First month review",          "Collect NPS score. Review ROI conversation. Start upsell conversation if appropriate."),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify_secret(secret: str) -> None:
    if INBOUND_SECRET and secret != INBOUND_SECRET:
        raise HTTPException(status_code=401, detail="Invalid inbound secret")


def _already_fired(hawk_user_id: str, trigger_type: str) -> bool:
    """Check if a nurture trigger has already fired for this user."""
    try:
        sb = get_supabase()
        res = (
            sb.table("trial_nurture_log")
            .select("id")
            .eq("hawk_user_id", hawk_user_id)
            .eq("trigger_type", trigger_type)
            .limit(1)
            .execute()
        )
        return len(res.data or []) > 0
    except Exception:
        return False


def _log_nurture(hawk_user_id: str, prospect_id: Optional[str], trigger_type: str, metadata: dict = {}) -> None:
    try:
        sb = get_supabase()
        sb.table("trial_nurture_log").insert({
            "hawk_user_id": hawk_user_id,
            "prospect_id": prospect_id,
            "trigger_type": trigger_type,
            "metadata": metadata,
        }).execute()
    except Exception as exc:
        logger.error("_log_nurture error: %s", exc)


def _find_or_create_prospect(domain: str, email: str, company: str, hawk_user_id: str) -> Optional[dict]:
    """Find existing prospect by domain or create new one for inbound signup."""
    try:
        sb = get_supabase()
        res = sb.table("prospects").select("*").eq("domain", domain).limit(1).execute()
        if res.data:
            prospect = res.data[0]
            sb.table("prospects").update({
                "hawk_user_id": hawk_user_id,
                "last_activity_at": _now(),
            }).eq("id", prospect["id"]).execute()
            return prospect

        return create_prospect({
            "domain": domain,
            "email": email,
            "company_name": company or domain.split(".")[0].title(),
            "source": "inbound_signup",
            "stage": "new",
            "hawk_user_id": hawk_user_id,
            "consent_basis": "implied",
            "last_activity_at": _now(),
        })
    except Exception as exc:
        logger.error("_find_or_create_prospect error: %s", exc)
        return None


def _auto_assign_rep(prospect_id: str, is_high_value: bool) -> Optional[str]:
    """
    Assign a rep based on capacity / high-value flag.
    High-value → assign senior rep (most closes in last 30 days).
    Standard → lowest current pipeline count (capacity-based round robin).
    Returns assigned rep_id or None.
    """
    try:
        sb = get_supabase()

        if is_high_value:
            # Assign to rep with most closes in last 30 days
            thirty_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            closes_res = (
                sb.table("clients")
                .select("closing_rep_id")
                .gte("close_date", thirty_ago)
                .execute()
            )
            from collections import Counter
            counts = Counter(c["closing_rep_id"] for c in (closes_res.data or []) if c.get("closing_rep_id"))
            best_rep_id = counts.most_common(1)[0][0] if counts else None
            if best_rep_id:
                sb.table("prospects").update({"assigned_rep_id": best_rep_id}).eq("id", prospect_id).execute()
                log_activity({
                    "prospect_id": prospect_id,
                    "type": "reassigned",
                    "metadata": {"new_rep_id": best_rep_id, "reason": "high_value_inbound"},
                })
                return best_rep_id

        # Capacity-based: rep with fewest active prospects
        reps_res = (
            sb.table("users")
            .select("id")
            .eq("role", "rep")
            .eq("status", "active")
            .execute()
        )
        if not reps_res.data:
            return None

        rep_ids = [r["id"] for r in reps_res.data]
        # Count active prospects per rep
        pipeline_res = (
            sb.table("prospects")
            .select("assigned_rep_id")
            .not_.in_("stage", ["closed_won", "lost"])
            .in_("assigned_rep_id", rep_ids)
            .execute()
        )
        from collections import Counter
        pipeline_counts = Counter(p["assigned_rep_id"] for p in (pipeline_res.data or []))
        # Pick rep with fewest (or zero) active prospects
        least_loaded = min(rep_ids, key=lambda r: pipeline_counts.get(r, 0))
        sb.table("prospects").update({"assigned_rep_id": least_loaded}).eq("id", prospect_id).execute()
        return least_loaded

    except Exception as exc:
        logger.error("_auto_assign_rep error: %s", exc)
        return None


def _create_onboarding_tasks(client_id: str, csm_rep_id: str, close_date: datetime) -> None:
    """Auto-create the 30-day onboarding task sequence for a new paid client."""
    try:
        sb = get_supabase()
        tasks = []
        for day_number, title, description in ONBOARDING_TASKS:
            due = close_date + timedelta(days=day_number)
            tasks.append({
                "client_id": client_id,
                "csm_rep_id": csm_rep_id,
                "day_number": day_number,
                "title": title,
                "description": description,
                "due_date": due.isoformat(),
                "status": "pending",
            })
        sb.table("onboarding_tasks").insert(tasks).execute()
        logger.info("Created %d onboarding tasks for client %s", len(tasks), client_id)
    except Exception as exc:
        logger.error("_create_onboarding_tasks failed: %s", exc)


async def _run_triage_scan(prospect: dict) -> None:
    """Fire HAWK scan on the inbound prospect's domain in background."""
    domain = prospect.get("domain", "")
    if not domain:
        return
    try:
        from backend.services.scanner import run_scan
        from backend.services.supabase_crm import get_supabase
        result = run_scan(domain, scan_id=None)
        hawk_score = result.get("score")
        if hawk_score is not None:
            sb = get_supabase()
            sb.table("prospects").update({
                "hawk_score": hawk_score,
                "last_scan_at": _now(),
            }).eq("id", prospect["id"]).execute()
            log_activity({
                "prospect_id": prospect["id"],
                "type": "scan_run",
                "metadata": {"hawk_score": hawk_score, "source": "inbound_triage"},
            })
    except Exception as exc:
        logger.error("Triage scan failed for domain %s: %s", domain, exc)


# ─── Models ───────────────────────────────────────────────────────────────────

class SignupPayload(BaseModel):
    hawk_user_id: str
    email: str
    company: Optional[str] = None
    domain: Optional[str] = None
    plan: str = "trial"              # trial, starter, shield, enterprise
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    secret: str = ""


class TrialEventPayload(BaseModel):
    hawk_user_id: str
    event: str       # never_scanned, ran_scan_no_upgrade, day7_features, day12_rep_task, day14_expiry, expired_no_convert
    email: Optional[str] = None
    domain: Optional[str] = None
    secret: str = ""


class PricingViewedPayload(BaseModel):
    hawk_user_id: str
    email: Optional[str] = None
    domain: Optional[str] = None
    secret: str = ""


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/signup")
async def inbound_signup(payload: SignupPayload, background_tasks: BackgroundTasks):
    """
    New HAWK signup webhook.
    Trial → creates CRM lead, runs triage scan, assigns rep or starts Charlotte nurture.
    Paid → creates/updates client record, assigns CSM, creates 30-day onboarding task sequence.
    """
    _verify_secret(payload.secret)

    if not supabase_available():
        logger.warning("inbound_signup: Supabase not configured")
        return {"status": "skipped"}

    domain = payload.domain or (payload.email.split("@")[-1] if payload.email and "@" in payload.email else "")
    if not domain:
        raise HTTPException(status_code=422, detail="domain or email required")

    is_paid = payload.plan in ("starter", "shield", "enterprise")

    # ── Find or create prospect ──────────────────────────────────────
    prospect = _find_or_create_prospect(
        domain=domain,
        email=payload.email,
        company=payload.company or "",
        hawk_user_id=payload.hawk_user_id,
    )
    if not prospect:
        raise HTTPException(status_code=500, detail="Failed to create prospect record")

    log_activity({
        "prospect_id": prospect["id"],
        "type": "stage_changed",
        "metadata": {"to_stage": "new", "source": "inbound_signup", "plan": payload.plan},
    })

    # ── Apollo enrichment (background) ───────────────────────────────
    # Enrichment service fires async — not blocking the webhook response
    # background_tasks.add_task(enrich_with_apollo, prospect["id"], domain)

    # ── Triage scan (background) ──────────────────────────────────────
    background_tasks.add_task(_run_triage_scan, prospect)

    if is_paid:
        # ── Paid signup: create/update client record ─────────────────
        sb = get_supabase()

        # Find existing client for this prospect or create new
        existing_client = (
            sb.table("clients")
            .select("id")
            .eq("prospect_id", prospect["id"])
            .limit(1)
            .execute()
        )

        if existing_client.data:
            client_id = existing_client.data[0]["id"]
            sb.table("clients").update({
                "hawk_user_id": payload.hawk_user_id,
                "plan": payload.plan,
                "stripe_customer_id": payload.stripe_customer_id,
                "stripe_subscription_id": payload.stripe_subscription_id,
                "status": "active",
            }).eq("id", client_id).execute()
        else:
            from backend.services.supabase_crm import PLAN_MRR  # type: ignore[attr-defined]
            mrr_map = {"starter": 99, "shield": 199, "enterprise": 399}
            mrr = mrr_map.get(payload.plan, 99)
            now = datetime.now(timezone.utc)
            clawback_deadline = (now + timedelta(days=90)).isoformat()

            client_res = sb.table("clients").insert({
                "prospect_id": prospect["id"],
                "hawk_user_id": payload.hawk_user_id,
                "plan": payload.plan,
                "mrr": mrr,
                "stripe_customer_id": payload.stripe_customer_id,
                "stripe_subscription_id": payload.stripe_subscription_id,
                "domain": domain,
                "company_name": payload.company or domain.split(".")[0].title(),
                "status": "active",
                "close_date": now.isoformat(),
                "clawback_deadline": clawback_deadline,
                "churn_risk_score": "low",
            }).execute()
            client_id = client_res.data[0]["id"] if client_res.data else None

        # ── Assign CSM (least-loaded CSM) ─────────────────────────────
        if client_id:
            csm_res = (
                sb.table("users")
                .select("id")
                .eq("role", "csm")
                .eq("status", "active")
                .limit(10)
                .execute()
            )
            csm_id = csm_res.data[0]["id"] if csm_res.data else None

            if csm_id:
                sb.table("clients").update({"csm_rep_id": csm_id}).eq("id", client_id).execute()
                background_tasks.add_task(
                    _create_onboarding_tasks,
                    client_id,
                    csm_id,
                    datetime.now(timezone.utc),
                )

        write_audit_log({
            "action": "client_inbound_signup",
            "record_type": "client",
            "record_id": client_id or prospect["id"],
            "new_value": {"plan": payload.plan, "hawk_user_id": payload.hawk_user_id},
        })
        return {
            "status": "processed",
            "type": "paid_signup",
            "prospect_id": prospect["id"],
            "client_id": client_id,
        }

    else:
        # ── Trial signup: score and assign ────────────────────────────
        # High-value = company found in Apollo with >50 employees or enterprise keyword
        # For now, use domain TLD heuristic (non-.com = smaller, .com = standard)
        is_high_value = not domain.endswith((".ca", ".co", ".io", ".dev"))

        rep_id = _auto_assign_rep(prospect["id"], is_high_value)

        if is_high_value and rep_id:
            # Notify rep immediately via WhatsApp
            try:
                sb_local = get_supabase()
                rep_res = sb_local.table("users").select("phone, full_name").eq("id", rep_id).single().execute()
                phone = (rep_res.data or {}).get("phone")
                if phone:
                    from backend.services.charlotte import send_whatsapp_alert
                    send_whatsapp_alert(
                        phone=phone,
                        message=f"🔥 High-value trial signup: {domain} — check your CRM dashboard now.",
                    )
            except Exception as exc:
                logger.debug("WhatsApp notification failed: %s", exc)

        else:
            # Standard trial → Charlotte nurture sequence
            log_activity({
                "prospect_id": prospect["id"],
                "type": "note_added",
                "notes": "Added to Charlotte nurture sequence (standard trial).",
                "metadata": {"source": "inbound_triage"},
            })

        return {
            "status": "processed",
            "type": "trial_signup",
            "prospect_id": prospect["id"],
            "assigned_rep_id": rep_id,
            "is_high_value": is_high_value,
        }


@router.post("/trial-event")
async def trial_event(payload: TrialEventPayload, background_tasks: BackgroundTasks):
    """
    Behaviour-triggered trial nurture events from HAWK product.
    Idempotent — each trigger_type fires at most once per user.
    """
    _verify_secret(payload.secret)

    if not supabase_available():
        return {"status": "skipped"}

    hawk_user_id = payload.hawk_user_id
    event = payload.event
    domain = payload.domain or (payload.email.split("@")[-1] if payload.email and "@" in payload.email else "")

    # Idempotency — don't fire the same trigger twice
    if _already_fired(hawk_user_id, event):
        return {"status": "already_fired", "event": event}

    sb = get_supabase()
    prospect = None
    if domain:
        res = sb.table("prospects").select("*").eq("domain", domain).limit(1).execute()
        if res.data:
            prospect = res.data[0]

    prospect_id = prospect["id"] if prospect else None

    if event == "never_scanned":
        # Day 1: Charlotte sends pre-run scan results for their domain
        log_activity({
            "prospect_id": prospect_id,
            "type": "note_added",
            "notes": "Trial nurture: user never ran a scan — Charlotte Day 1 email queued.",
            "metadata": {"trigger": event},
        })

    elif event == "ran_scan_no_upgrade":
        # Day 2: personalised findings summary with upgrade CTA
        log_activity({
            "prospect_id": prospect_id,
            "type": "note_added",
            "notes": "Trial nurture: user ran scan but didn't upgrade — Charlotte Day 2 findings email queued.",
            "metadata": {"trigger": event},
        })

    elif event == "day7_features":
        # Day 7: unused features walkthrough
        log_activity({
            "prospect_id": prospect_id,
            "type": "note_added",
            "notes": "Trial nurture: Day 7 — Charlotte unused features walkthrough email queued.",
            "metadata": {"trigger": event},
        })

    elif event == "day12_rep_task":
        # Day 12: rep task to call
        if prospect_id:
            rep_id = prospect.get("assigned_rep_id") if prospect else None
            log_activity({
                "prospect_id": prospect_id,
                "type": "note_added",
                "notes": "⏰ Trial Day 12 — 2 days left. Call this trial now for last-chance conversion.",
                "metadata": {"urgent": True, "trigger": event, "rep_id": rep_id},
            })

    elif event == "day14_expiry":
        # Day 14: rep task + WhatsApp
        if prospect_id:
            rep_id = prospect.get("assigned_rep_id") if prospect else None
            log_activity({
                "prospect_id": prospect_id,
                "type": "note_added",
                "notes": "🚨 Trial expired today — call NOW for last-chance offer.",
                "metadata": {"urgent": True, "trigger": event},
            })
            if rep_id:
                try:
                    rep_res = sb.table("users").select("phone").eq("id", rep_id).single().execute()
                    phone = (rep_res.data or {}).get("phone")
                    if phone:
                        from backend.services.charlotte import send_whatsapp_alert
                        send_whatsapp_alert(
                            phone=phone,
                            message=f"🚨 Trial expired: {domain} — call today for last-chance offer.",
                        )
                except Exception as exc:
                    logger.debug("WhatsApp failed for day14_expiry: %s", exc)

    elif event == "expired_no_convert":
        # Move to Lost, set reactivation date 30 days out
        if prospect_id:
            reactivate_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            sb.table("prospects").update({
                "stage": "lost",
                "lost_reason": "Trial expired — no conversion",
                "reactivate_date": reactivate_date,
                "last_activity_at": _now(),
            }).eq("id", prospect_id).execute()
            log_activity({
                "prospect_id": prospect_id,
                "type": "stage_changed",
                "metadata": {"to_stage": "lost", "reason": "trial_expired", "reactivate_date": reactivate_date},
            })

    _log_nurture(hawk_user_id, prospect_id, event, {"domain": domain})
    return {"status": "processed", "event": event, "prospect_id": prospect_id}


@router.post("/pricing-viewed")
async def pricing_viewed(payload: PricingViewedPayload):
    """Trial user viewed the pricing page — immediate rep notification."""
    _verify_secret(payload.secret)

    if not supabase_available():
        return {"status": "skipped"}

    hawk_user_id = payload.hawk_user_id

    # Only notify once per user
    if _already_fired(hawk_user_id, "viewed_pricing"):
        return {"status": "already_fired"}

    domain = payload.domain or (payload.email.split("@")[-1] if payload.email and "@" in payload.email else "")
    sb = get_supabase()
    prospect = None
    if domain:
        res = sb.table("prospects").select("*").eq("domain", domain).limit(1).execute()
        prospect = res.data[0] if res.data else None

    prospect_id = prospect["id"] if prospect else None

    log_activity({
        "prospect_id": prospect_id,
        "type": "note_added",
        "notes": f"🔥 Trial user from {domain} just viewed the pricing page — call now.",
        "metadata": {"urgent": True, "trigger": "viewed_pricing"},
    })

    # WhatsApp rep
    if prospect and prospect.get("assigned_rep_id"):
        try:
            rep_res = sb.table("users").select("phone").eq("id", prospect["assigned_rep_id"]).single().execute()
            phone = (rep_res.data or {}).get("phone")
            if phone:
                from backend.services.charlotte import send_whatsapp_alert
                send_whatsapp_alert(
                    phone=phone,
                    message=f"🔥 {domain} just viewed pricing — they're hot. Call now.",
                )
        except Exception as exc:
            logger.debug("WhatsApp failed for pricing_viewed: %s", exc)

    _log_nurture(hawk_user_id, prospect_id, "viewed_pricing", {"domain": domain})
    return {"status": "processed", "prospect_id": prospect_id}
