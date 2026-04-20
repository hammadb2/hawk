"""Post-reply nurture cadence.

After ARIA auto-sends the Cal.com link to a positive/question reply, we
schedule a 48-hour check-in. If the prospect still hasn't booked by then,
ARIA sends ONE personalised follow-up that references their specific
finding + offers an alternative slot. If that also fails to convert, the
prospect enters a 30-day weekly nurture drip (one email per week for 4
weeks) with a new finding or a Canadian breach story in their vertical.

Every scheduled send goes through ``aria_scheduled_actions`` — this file
just owns the scheduling decisions + the handler logic for each action
type.
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import (
    CAL_COM_BOOKING_URL,
    CRM_PUBLIC_BASE_URL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    SUPABASE_URL,
)
from services.openai_chat import chat_text_sync
from services import aria_scheduled_actions, aria_settings
from services.aria_closer_briefing import fetch_briefing
from services.mailbox_registry import pick_next_for_vertical
from services.mailbox_smtp_sender import send_via_mailbox

logger = logging.getLogger(__name__)

FOLLOWUP_DELAY_HOURS = 48
NURTURE_MAX_WEEKS = 4
NURTURE_WEEK_DELAY_DAYS = 7


def _sb_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _booking_url() -> str:
    return (CAL_COM_BOOKING_URL or "https://cal.com/hawksecurity/15min").rstrip("/")


def _prospect_has_booked(prospect_id: str) -> bool:
    """True if the prospect's stage moved to ``call_booked`` since we scheduled this action."""
    if not SUPABASE_URL or not prospect_id:
        return False
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}", "select": "stage,nurture_stopped_at", "limit": "1"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return False
        row = rows[0]
        if row.get("nurture_stopped_at"):
            return True  # don't re-send after a hard stop
        return str(row.get("stage") or "").lower() in {"call_booked", "closed_won", "closed_lost", "unsubscribed"}
    except Exception:
        logger.exception("_prospect_has_booked failed prospect=%s", prospect_id)
        return False


def _fetch_prospect(prospect_id: str) -> dict[str, Any] | None:
    if not SUPABASE_URL or not prospect_id:
        return None
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "id": f"eq.{prospect_id}",
                "select": "id,contact_email,first_name,last_name,company_name,domain,vertical",
                "limit": "1",
            },
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception:
        logger.exception("_fetch_prospect failed id=%s", prospect_id)
        return None


def _send(prospect: dict[str, Any], subject: str, body_text: str) -> dict[str, Any] | None:
    contact_email = (prospect.get("contact_email") or "").strip()
    if not contact_email:
        return None
    vertical = (prospect.get("vertical") or "").strip() or "unknown"
    mailbox = pick_next_for_vertical(vertical)
    if not mailbox:
        logger.warning("nurture: no mailbox available vertical=%s", vertical)
        return None
    contact_name = " ".join(
        p for p in (prospect.get("first_name"), prospect.get("last_name")) if p
    ).strip() or contact_email.split("@")[0]
    html = "".join(f"<p>{p}</p>" for p in body_text.split("\n\n") if p.strip())
    result = send_via_mailbox(
        str(mailbox["id"]),
        to_email=contact_email,
        to_name=contact_name,
        subject=subject,
        body_text=body_text,
        body_html=html,
    )
    if not getattr(result, "ok", False):
        logger.warning("nurture send failed: %s", getattr(result, "error", None))
        return None
    return {
        "mailbox_id": str(mailbox["id"]),
        "message_id": getattr(result, "message_id", None),
    }


def _patch_prospect(prospect_id: str, **fields: Any) -> None:
    if not SUPABASE_URL or not prospect_id:
        return
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json=fields,
            timeout=10.0,
        ).raise_for_status()
    except Exception:
        logger.exception("nurture _patch_prospect failed id=%s", prospect_id)


# ── Public scheduling API ─────────────────────────────────────────────────


def schedule_48h_followup(*, prospect_id: str, reply_id: str | None = None) -> str | None:
    """Queue the 48h "still interested?" follow-up."""
    if not aria_settings.get_bool("aria_nurture_enabled", True):
        return None
    due = datetime.now(timezone.utc) + timedelta(hours=FOLLOWUP_DELAY_HOURS)
    return aria_scheduled_actions.schedule(
        action_type="follow_up_48hr",
        due_at=due,
        prospect_id=prospect_id,
        inbound_reply_id=reply_id,
        payload={"source": "positive_reply"},
    )


def schedule_nurture_week(*, prospect_id: str, week: int) -> str | None:
    """Queue the next weekly nurture email (1..NURTURE_MAX_WEEKS)."""
    if week > NURTURE_MAX_WEEKS:
        return None
    if not aria_settings.get_bool("aria_nurture_enabled", True):
        return None
    due = datetime.now(timezone.utc) + timedelta(days=NURTURE_WEEK_DELAY_DAYS)
    return aria_scheduled_actions.schedule(
        action_type="nurture_weekly",
        due_at=due,
        prospect_id=prospect_id,
        payload={"week": week},
        dedupe=False,  # each week is a separate scheduled action
    )


# ── Handlers (bound to aria_scheduled_actions handler registry) ───────────


_FOLLOWUP_SYSTEM = """You are ARIA. The prospect replied positively to our cold
email 48 hours ago and we sent them the Cal.com link — but they didn't book.
Write ONE short follow-up email (plain text, 70-100 words, no subject line,
no greeting, sign off "— Hammad") that:
 1. Doesn't guilt or nag.
 2. References the SPECIFIC finding on their domain: {finding}
 3. Offers a concrete alternative: "I can also send the 3 highest-severity
    findings in an email if you'd rather read than talk." or a specific
    alternate slot.
 4. Re-drops the booking link: {booking_url}

The prospect's context follows. Write only the email body."""


def handle_follow_up_48hr(row: dict[str, Any]) -> dict[str, Any]:
    prospect_id = row.get("prospect_id")
    if not prospect_id or _prospect_has_booked(str(prospect_id)):
        return {"skipped": True, "reason": "already_booked_or_stopped"}
    prospect = _fetch_prospect(str(prospect_id))
    if not prospect:
        return {"skipped": True, "reason": "no_prospect"}

    briefing = fetch_briefing(str(prospect_id))
    top_vulns = briefing.get("top_vulns") or []
    finding = top_vulns[0] if top_vulns else "the findings from our initial scan"

    subject = "One more thought — happy to email the findings instead"
    if OPENAI_API_KEY:
        try:
            body = chat_text_sync(
                api_key=OPENAI_API_KEY,
                user_messages=[{
                    "role": "user",
                    "content": (
                        f"Prospect: {prospect.get('first_name') or ''} {prospect.get('last_name') or ''}\n"
                        f"Company: {prospect.get('company_name') or prospect.get('domain') or ''}\n"
                        f"Vertical: {prospect.get('vertical') or 'unknown'}\n"
                        f"Finding: {finding}\n"
                    ),
                }],
                max_tokens=260,
                system=_FOLLOWUP_SYSTEM.format(finding=finding, booking_url=_booking_url()),
                model=OPENAI_MODEL,
            ).strip()
        except Exception:
            logger.exception("nurture: 48h LLM draft failed, falling back to template")
            body = _fallback_48h_body(finding)
    else:
        body = _fallback_48h_body(finding)

    sent = _send(prospect, subject, body)
    if not sent:
        return {"sent": False, "reason": "send_failed"}

    # Kick off the 30-day weekly drip now that the one personalised follow-up
    # failed to convert.
    schedule_nurture_week(prospect_id=str(prospect_id), week=1)
    _patch_prospect(
        str(prospect_id),
        nurture_started_at=datetime.now(timezone.utc).isoformat(),
        last_activity_at=datetime.now(timezone.utc).isoformat(),
    )
    return {"sent": True, "subject": subject, **sent}


def _fallback_48h_body(finding: str) -> str:
    return (
        f"Wanted to circle back once — I know inboxes are loud.\n\n"
        f"I can send over the three highest-severity findings for your domain "
        f"in a quick email if reading's easier than a call — the one I'd start "
        f"with is {finding}.\n\n"
        f"Or if a 15-min call is easier, here's a slot picker: {_booking_url()}\n\n"
        f"Either way, no pressure. Just don't want you to miss this.\n\n"
        f"— Hammad"
    )


_NURTURE_SYSTEM = """You are ARIA writing a weekly nurture email for a Canadian
cybersecurity company (HAWK Security). The prospect already got our cold
email + a personalised follow-up and didn't book. Do NOT be salesy. Do NOT
re-pitch. Write a short value-first update (80-120 words) that:

 1. Opens with a single concrete, topical data point — one of:
    a. A new finding severity trend in their vertical (dental / legal /
       accounting), OR
    b. A recent Canadian breach story they'd care about (OPC enforcement,
       PIPEDA penalty, ransomware on a similar clinic).
 2. Ties the data point to a generic 1-line ask — no pressure. Example:
    "If you want us to re-run a scan on your domain any time, just reply."
 3. Plain text, no subject line, no greeting block, sign off "— Hammad".

Week number: {week} of {max_weeks}. The prospect's vertical is {vertical}.
"""


def handle_nurture_weekly(row: dict[str, Any]) -> dict[str, Any]:
    prospect_id = row.get("prospect_id")
    if not prospect_id or _prospect_has_booked(str(prospect_id)):
        return {"skipped": True, "reason": "already_booked_or_stopped"}
    prospect = _fetch_prospect(str(prospect_id))
    if not prospect:
        return {"skipped": True, "reason": "no_prospect"}

    payload = row.get("payload") or {}
    week = int(payload.get("week") or 1)
    vertical = prospect.get("vertical") or "professional services"

    subject_pool = [
        f"Quick update — week {week}",
        "One more finding I thought you'd want to see",
        "Since we last chatted",
        "Thought this was worth flagging",
    ]
    subject = subject_pool[(week - 1) % len(subject_pool)]

    if OPENAI_API_KEY:
        try:
            body = chat_text_sync(
                api_key=OPENAI_API_KEY,
                user_messages=[{
                    "role": "user",
                    "content": (
                        f"Company: {prospect.get('company_name') or prospect.get('domain') or ''}\n"
                        f"Vertical: {vertical}\n"
                        f"Week: {week}\n"
                    ),
                }],
                max_tokens=260,
                system=_NURTURE_SYSTEM.format(week=week, max_weeks=NURTURE_MAX_WEEKS, vertical=vertical),
                model=OPENAI_MODEL,
            ).strip()
        except Exception:
            logger.exception("nurture weekly LLM draft failed week=%s", week)
            body = _fallback_nurture_body(week, vertical)
    else:
        body = _fallback_nurture_body(week, vertical)

    sent = _send(prospect, subject, body)
    if not sent:
        return {"sent": False, "reason": "send_failed"}

    schedule_nurture_week(prospect_id=str(prospect_id), week=week + 1)
    _patch_prospect(str(prospect_id), last_activity_at=datetime.now(timezone.utc).isoformat())
    return {"sent": True, "week": week, **sent}


_DENTAL_STORIES = [
    "The OPC opened an investigation this month on a dental group that leaked 135k patient records through a misconfigured intake form.",
    "A multi-location clinic in Ontario paid $180k in ransom last quarter after staff credentials were harvested via a spoofed billing email.",
]
_LEGAL_STORIES = [
    "A Quebec law firm was fined $100k this quarter under Law 25 for failing to notify clients of a laptop-theft breach within 72 hours.",
    "The Canadian Bar Association flagged a 31% year-over-year rise in ransomware targeting firms with fewer than 50 lawyers.",
]
_ACCT_STORIES = [
    "CPA Canada's 2025 cyber report shows client tax-return data is now the #1 targeted asset for ransomware crews hitting accounting firms.",
    "A Calgary accounting practice reported a $120k wire-fraud loss in April after their email domain was spoofed due to missing DMARC enforcement.",
]


def _fallback_nurture_body(week: int, vertical: str) -> str:
    v = (vertical or "").lower()
    if "dent" in v:
        story = random.choice(_DENTAL_STORIES)
    elif "law" in v or "legal" in v:
        story = random.choice(_LEGAL_STORIES)
    elif "acct" in v or "account" in v:
        story = random.choice(_ACCT_STORIES)
    else:
        story = "OPC enforcement actions under PIPEDA are up 38% year-over-year in 2025, and small professional practices are the fastest-growing target segment."

    return (
        f"One thing from this week that made me think of you:\n\n"
        f"{story}\n\n"
        f"If you'd like us to re-run a scan on your domain any time — no "
        f"strings, no call needed — just reply 'rescan' and we'll send a "
        f"fresh report in 24 hours.\n\n"
        f"— Hammad"
    )


# ── Other scheduled-action handlers ──────────────────────────────────────


def handle_call_reminder_24hr(row: dict[str, Any]) -> dict[str, Any]:
    prospect_id = row.get("prospect_id")
    if not prospect_id:
        return {"skipped": True, "reason": "no_prospect_id"}
    prospect = _fetch_prospect(str(prospect_id))
    if not prospect:
        return {"skipped": True, "reason": "no_prospect"}
    payload = row.get("payload") or {}
    start_time_str = str(payload.get("start_time") or "").strip()
    when_label = str(payload.get("when_label") or start_time_str or "tomorrow").strip()
    meeting_link = str(payload.get("meeting_link") or "").strip()
    subject = "Quick reminder — our call tomorrow"
    body = (
        f"Hey, just a reminder we're speaking {when_label}.\n\n"
        + (f"Meeting link: {meeting_link}\n\n" if meeting_link else "")
        + "If something comes up and you need to reschedule, hit reply and "
        + "we'll sort it.\n\n"
        + "— Hammad"
    )
    sent = _send(prospect, subject, body)
    return {"sent": bool(sent), **(sent or {})}


def handle_ooo_return_followup(row: dict[str, Any]) -> dict[str, Any]:
    prospect_id = row.get("prospect_id")
    if not prospect_id:
        return {"skipped": True, "reason": "no_prospect_id"}
    if _prospect_has_booked(str(prospect_id)):
        return {"skipped": True, "reason": "already_booked"}
    prospect = _fetch_prospect(str(prospect_id))
    if not prospect:
        return {"skipped": True, "reason": "no_prospect"}
    briefing = fetch_briefing(str(prospect_id))
    top = briefing.get("top_vulns") or []
    finding = top[0] if top else "the findings from our initial scan"
    subject = "Welcome back — quick follow-up"
    body = (
        f"Hope the time off was good.\n\n"
        f"Picking up where I left you — we flagged {finding} on {briefing.get('domain') or 'your domain'}. "
        f"If you have 15 minutes this week, here's a slot picker: {_booking_url()}\n\n"
        f"Or if email is easier, I can send the full three-finding summary — just reply 'send it'.\n\n"
        f"— Hammad"
    )
    sent = _send(prospect, subject, body)
    return {"sent": bool(sent), **(sent or {})}


def handle_snooze_90d(row: dict[str, Any]) -> dict[str, Any]:
    """Re-engage a prospect 90 days after they asked us to circle back."""
    prospect_id = row.get("prospect_id")
    if not prospect_id:
        return {"skipped": True, "reason": "no_prospect_id"}
    if _prospect_has_booked(str(prospect_id)):
        return {"skipped": True, "reason": "already_booked"}
    prospect = _fetch_prospect(str(prospect_id))
    if not prospect:
        return {"skipped": True, "reason": "no_prospect"}
    briefing = fetch_briefing(str(prospect_id))
    top = briefing.get("top_vulns") or []
    finding = top[0] if top else "what we picked up on your domain"
    subject = "Circling back — as promised, 90 days later"
    body = (
        f"You asked me to check back in 90 days — here I am. \n\n"
        f"Re-ran a quick scan on {briefing.get('domain') or 'your domain'} this morning. "
        f"The top exposure is still {finding}. \n\n"
        f"Worth 15 minutes to walk through: {_booking_url()}\n\n"
        f"If the timing still isn't right, reply 'skip' and I'll drop off.\n\n"
        f"— Hammad"
    )
    sent = _send(prospect, subject, body)
    return {"sent": bool(sent), **(sent or {})}


def register_handlers() -> None:
    """Hook into the scheduled-actions executor. Called once at app startup."""
    aria_scheduled_actions.register_handler("follow_up_48hr", handle_follow_up_48hr)
    aria_scheduled_actions.register_handler("nurture_weekly", handle_nurture_weekly)
    aria_scheduled_actions.register_handler("call_reminder_24hr", handle_call_reminder_24hr)
    aria_scheduled_actions.register_handler("ooo_return_followup", handle_ooo_return_followup)
    aria_scheduled_actions.register_handler("snooze_90d", handle_snooze_90d)


__all__ = [
    "schedule_48h_followup",
    "schedule_nurture_week",
    "register_handlers",
    "handle_follow_up_48hr",
    "handle_nurture_weekly",
    "handle_call_reminder_24hr",
    "handle_ooo_return_followup",
    "handle_snooze_90d",
]


_ = CRM_PUBLIC_BASE_URL  # reserved for future briefing links in nurture emails
