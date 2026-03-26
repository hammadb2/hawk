"""
CRM Charlotte Router
Handles Smartlead webhook events and Charlotte reporting/assignment.
All DB writes use the Supabase service client (bypassing RLS — webhook context).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.services.supabase_crm import (
    supabase_available,
    get_supabase,
    get_prospect_by_domain,
    create_prospect,
    update_prospect,
    upsert_email_event,
    update_email_event_by_prospect,
    log_activity,
    add_to_suppression_list,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm", tags=["crm-charlotte"])

# ─── Webhook Models ───────────────────────────────────────────────────────────

VALID_SMARTLEAD_EVENTS = [
    "email_sent",
    "email_opened",
    "email_clicked",
    "email_replied",
    "email_unsubscribed",
    "email_bounced",
]

POSITIVE_KEYWORDS = ["interested", "yes", "sure", "let's", "schedule", "call", "demo", "pricing", "how much", "cost"]
NEGATIVE_KEYWORDS = ["not interested", "remove me", "unsubscribe", "stop emailing", "don't contact"]
OOO_KEYWORDS = ["out of office", "ooo", "on vacation", "on leave", "returning", "away until"]


def classify_reply_sentiment(text: str) -> str:
    lower = text.lower()
    if any(kw in lower for kw in OOO_KEYWORDS):
        return "ooo"
    if any(kw in lower for kw in NEGATIVE_KEYWORDS):
        return "negative"
    if any(kw in lower for kw in POSITIVE_KEYWORDS):
        return "positive"
    return "question"


def _extract_domain(email: str) -> str:
    return email.split("@")[-1].lower() if "@" in email else email.lower()


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/webhooks/smartlead")
async def smartlead_webhook(request: Request):
    """
    Receive and process Smartlead webhook events.

    email_sent        → Create prospect if domain not in CRM, log email_event
    email_opened      → Update open_count/opened_at; flag hot if >=3 opens
    email_clicked     → Update click_count/clicked_at
    email_replied     → Classify sentiment; positive → flag hot, move to Replied
    email_unsubscribed → Add to suppressions, mark Lost
    email_bounced     → Add to suppressions, flag domain
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = body.get("event_type", "")
    if event_type not in VALID_SMARTLEAD_EVENTS:
        return {"status": "ignored", "event_type": event_type}

    email: str = body.get("email", "").lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Valid email is required")

    domain = _extract_domain(email)
    now = datetime.now(timezone.utc).isoformat()

    if not supabase_available():
        logger.warning("Supabase not configured — webhook event %s not persisted", event_type)
        return {"status": "skipped", "reason": "supabase_not_configured", "event_type": event_type}

    # ── Find or create prospect ───────────────────────────────────────────────
    prospect = get_prospect_by_domain(domain)

    if event_type == "email_sent":
        if not prospect:
            # Charlotte auto-creates prospect
            prospect = create_prospect({
                "domain": domain,
                "company_name": domain.split(".")[0].title(),  # Placeholder — enriched by Apollo
                "source": "charlotte",
                "stage": "new",
                "consent_basis": "implied",
                "last_activity_at": now,
            })
            logger.info("Charlotte created prospect: %s", domain)
        else:
            update_prospect(prospect["id"], {"last_activity_at": now})

        if prospect:
            upsert_email_event(prospect["id"], {
                "smartlead_event_type": "email_sent",
                "subject": body.get("subject"),
                "sequence_step": body.get("sequence_step"),
                "sent_at": now,
            })

    elif event_type == "email_opened" and prospect:
        # Deduplicate rapid opens (bot detection — multiple from same IP within 1 min handled by Smartlead)
        sb = get_supabase()
        latest = (
            sb.table("email_events")
            .select("id, open_count")
            .eq("prospect_id", prospect["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if latest.data:
            new_count = (latest.data[0].get("open_count") or 0) + 1
            sb.table("email_events").update({
                "opened_at": now,
                "open_count": new_count,
            }).eq("id", latest.data[0]["id"]).execute()

            # Auto-hot-flag after 3+ opens
            if new_count >= 3 and not prospect.get("is_hot"):
                update_prospect(prospect["id"], {"is_hot": True, "last_activity_at": now})
                log_activity({
                    "prospect_id": prospect["id"],
                    "type": "hot_flagged",
                    "metadata": {"reason": f"Opened email {new_count} times"},
                })
                logger.info("Auto hot-flagged prospect %s (opened %d times)", domain, new_count)

    elif event_type == "email_clicked" and prospect:
        sb = get_supabase()
        latest = (
            sb.table("email_events")
            .select("id, click_count")
            .eq("prospect_id", prospect["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if latest.data:
            new_count = (latest.data[0].get("click_count") or 0) + 1
            sb.table("email_events").update({
                "clicked_at": now,
                "click_count": new_count,
            }).eq("id", latest.data[0]["id"]).execute()

        # Move to Replied stage if not already past it
        past_replied = ["replied", "call_booked", "proposal_sent", "closed_won", "lost"]
        if prospect and prospect.get("stage") not in past_replied:
            update_prospect(prospect["id"], {
                "stage": "replied",
                "last_activity_at": now,
            })

    elif event_type == "email_replied" and prospect:
        reply_text = body.get("reply_text", "")
        sentiment = classify_reply_sentiment(reply_text)

        # Ignore OOO — don't update stage or flag
        if sentiment != "ooo":
            update_email_event_by_prospect(prospect["id"], {
                "replied_at": now,
                "reply_sentiment": sentiment,
            })

            past_replied = ["call_booked", "proposal_sent", "closed_won", "lost"]
            if prospect.get("stage") not in past_replied:
                update_prospect(prospect["id"], {
                    "stage": "replied",
                    "last_activity_at": now,
                })

            if sentiment == "positive":
                update_prospect(prospect["id"], {"is_hot": True, "last_activity_at": now})
                log_activity({
                    "prospect_id": prospect["id"],
                    "type": "hot_flagged",
                    "metadata": {"reason": "Positive reply from Charlotte sequence"},
                })
                logger.info("Positive reply from %s — flagged hot", domain)

    elif event_type == "email_unsubscribed":
        add_to_suppression_list(domain, email, "unsubscribe")
        if prospect:
            update_prospect(prospect["id"], {
                "stage": "lost",
                "lost_reason": "Unsubscribed",
                "last_activity_at": now,
            })
            log_activity({
                "prospect_id": prospect["id"],
                "type": "stage_changed",
                "metadata": {"to_stage": "lost", "reason": "Unsubscribed"},
            })
        logger.info("Unsubscribe — added %s to suppression list", domain)

    elif event_type == "email_bounced":
        add_to_suppression_list(domain, email, "bounce")
        if prospect:
            update_prospect(prospect["id"], {"last_activity_at": now})
        logger.info("Hard bounce — added %s to suppression list", domain)

    return {
        "status": "processed",
        "event_type": event_type,
        "domain": domain,
        "processed_at": now,
    }


@router.get("/charlotte/stats")
async def charlotte_stats():
    """Aggregate today's Charlotte stats from email_events."""
    if not supabase_available():
        return _empty_stats()

    try:
        sb = get_supabase()
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        sent = sb.table("email_events").select("id", count="exact").gte("sent_at", today).eq("smartlead_event_type", "email_sent").execute()
        opened = sb.table("email_events").select("id", count="exact").gte("opened_at", today).execute()
        replied = sb.table("email_events").select("id", count="exact").gte("replied_at", today).execute()
        positive = sb.table("email_events").select("id", count="exact").gte("replied_at", today).eq("reply_sentiment", "positive").execute()
        new_prospects = sb.table("prospects").select("id", count="exact").gte("created_at", today).eq("source", "charlotte").execute()

        return {
            "sent_today": sent.count or 0,
            "opened_today": opened.count or 0,
            "replied_today": replied.count or 0,
            "positive_replies": positive.count or 0,
            "prospects_created": new_prospects.count or 0,
            "closes_attributed": 0,  # TODO: join with clients.source = 'charlotte'
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "status": "healthy",
        }
    except Exception as e:
        logger.error("charlotte_stats error: %s", e)
        return _empty_stats()


def _empty_stats() -> dict:
    return {
        "sent_today": 0,
        "opened_today": 0,
        "replied_today": 0,
        "positive_replies": 0,
        "prospects_created": 0,
        "closes_attributed": 0,
        "last_ping": datetime.now(timezone.utc).isoformat(),
        "status": "healthy" if supabase_available() else "degraded",
    }


@router.get("/charlotte/domains")
async def charlotte_domains():
    """Sending domain health — aggregated from email_events."""
    # In production, this would query Smartlead API for domain health metrics.
    # Returning placeholder structure for frontend to render.
    return {"domains": []}


@router.get("/charlotte/sequences")
async def charlotte_sequences():
    """Sequence performance — aggregate email events by sequence step."""
    if not supabase_available():
        return {"sequences": []}

    try:
        sb = get_supabase()
        res = (
            sb.table("email_events")
            .select("sequence_step, open_count, click_count, replied_at, reply_sentiment")
            .not_.is_("sequence_step", "null")
            .execute()
        )
        # Group by sequence step
        from collections import defaultdict
        steps: dict = defaultdict(lambda: {"sends": 0, "opens": 0, "clicks": 0, "replies": 0})
        for row in (res.data or []):
            step = row.get("sequence_step", 0)
            steps[step]["sends"] += 1
            if row.get("open_count", 0) > 0:
                steps[step]["opens"] += 1
            if row.get("click_count", 0) > 0:
                steps[step]["clicks"] += 1
            if row.get("replied_at"):
                steps[step]["replies"] += 1

        sequences = []
        for step, counts in sorted(steps.items()):
            s = counts["sends"] or 1
            sequences.append({
                "step": step,
                "send_count": counts["sends"],
                "open_rate": round(counts["opens"] / s * 100, 1),
                "click_rate": round(counts["clicks"] / s * 100, 1),
                "reply_rate": round(counts["replies"] / s * 100, 1),
            })

        return {"sequences": sequences}
    except Exception as e:
        logger.error("charlotte_sequences error: %s", e)
        return {"sequences": []}


class AssignRequest(BaseModel):
    prospect_id: str
    rep_id: str


@router.post("/charlotte/assign")
async def assign_prospect(body: AssignRequest):
    """Manually assign an unassigned Charlotte prospect to a rep."""
    if not supabase_available():
        raise HTTPException(status_code=503, detail="Supabase not configured")

    result = update_prospect(body.prospect_id, {
        "assigned_rep_id": body.rep_id,
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
    })
    if not result:
        raise HTTPException(status_code=404, detail="Prospect not found")

    log_activity({
        "prospect_id": body.prospect_id,
        "type": "reassigned",
        "metadata": {"new_rep_id": body.rep_id},
    })

    return {"id": body.prospect_id, "assigned_rep_id": body.rep_id}


class AssignmentRulesRequest(BaseModel):
    mode: str
    config: Optional[Dict[str, Any]] = None


@router.put("/charlotte/assignment-rules")
async def update_assignment_rules(body: AssignmentRulesRequest):
    """Update Charlotte's lead assignment configuration."""
    valid_modes = ["round_robin", "by_industry", "by_city", "by_capacity"]
    if body.mode not in valid_modes:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mode. Must be one of: {valid_modes}"
        )
    # In production: persist to a settings/config table
    return {"success": True, "mode": body.mode}
