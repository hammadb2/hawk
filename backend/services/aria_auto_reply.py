"""Autonomous reply orchestrator.

Called from ``aria_reply_handler.process_reply_event`` after classification.
Decides whether to auto-send via the mailbox SMTP dispatcher (PR #35), route
the reply to the VA queue for human touch, schedule a follow-up, or suppress
the contact — all without a human in the loop.

Flow per sentiment:
 * ``positive``                      → KB-grounded draft + Cal link + send + 48h follow-up scheduled
 * ``question``                      → same, with explicit KB answer prepended
 * ``objection``                     → playbook response (price / provider / busy / not_interested)
 * ``not_interested`` (90-day snooze) → polite close, schedule re-engagement
 * ``out_of_office``                 → parse return date, schedule follow-up
 * ``unsubscribe``                   → add to suppressions, never respond
 * ``other``                         → route to VA queue, no send

All outbound mail goes through the same round-robin mailbox SMTP dispatcher
the cold send uses, so threading + DKIM alignment + daily caps are already
taken care of.
"""

from __future__ import annotations

import logging
import os
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
from services import (
    aria_human_checkpoint,
    aria_knowledge_base,
    aria_ooo_parser,
    aria_scheduled_actions,
    aria_settings,
)
from services.crm_openphone import send_ceo_sms, send_sms
from services.mailbox_registry import pick_next_for_vertical
from services.mailbox_smtp_sender import send_via_mailbox

logger = logging.getLogger(__name__)


# ── Settings / helpers ────────────────────────────────────────────────────


def _sb_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def autonomous_reply_enabled() -> bool:
    from config import ARIA_AUTONOMOUS_REPLY_ENABLED
    override = (ARIA_AUTONOMOUS_REPLY_ENABLED or "").strip().lower()
    if override in ("false", "0", "no", "off"):
        return False
    if override in ("true", "1", "yes", "on"):
        return True
    return aria_settings.get_bool("autonomous_reply_enabled", True)


def _booking_url() -> str:
    return (CAL_COM_BOOKING_URL or "https://cal.com/hawksecurity/15min").rstrip("/")


def _build_context(
    prospect_name: str | None,
    company_name: str | None,
    vertical: str | None,
    vulnerability: str | None,
    reply_subject: str,
    reply_body: str,
) -> str:
    parts = [
        f"Prospect name: {prospect_name or 'unknown'}",
        f"Company: {company_name or 'unknown'}",
        f"Vertical: {vertical or 'unknown'}",
    ]
    if vulnerability:
        parts.append(f"Top finding from our scan: {vulnerability}")
    parts.append(f"Reply subject: {reply_subject or '(none)'}")
    parts.append(f"Reply body:\n{(reply_body or '')[:2000]}")
    return "\n".join(parts)


def _add_reply_quote(reply_body: str) -> str:
    clean = (reply_body or "").strip()
    if not clean:
        return ""
    quoted = "\n".join(f"> {line}" for line in clean.splitlines()[:20])
    return "\n\n-----\n" + quoted


# ── LLM drafting ──────────────────────────────────────────────────────────


_POSITIVE_SYSTEM = """You are ARIA, a reply-drafting assistant for HAWK Security —
a Canadian managed-cybersecurity company.

A prospect has just replied POSITIVELY to our cold email. Your job is to
respond briefly and book a 15-minute call. You must:

1. Acknowledge what they actually said in one short sentence.
2. If they asked ANY question, answer it directly, grounded in the KB below.
   Do NOT invent pricing, tiers, or claims. If the KB doesn't cover it, say
   "I'll confirm that on our call" rather than guessing.
3. Drop this exact booking link with a concrete CTA that references their
   specific finding if one is given:
       {booking_url}
4. Keep the whole thing under 110 words. Plain text. No subject line, no
   greeting block, no signature. Sign off with "— Hammad".

Tone: peer to peer, zero sales jargon, zero "I hope this email finds you
well", zero bold claims. Write the way a founder writes on a phone.

Knowledge base (authoritative — do not contradict):
---
{kb}
---
"""

_QUESTION_SYSTEM = """You are ARIA, a reply-drafting assistant for HAWK Security.

A prospect asked a specific question in their reply. Your job is to:
1. Answer their question directly in 1-3 sentences, grounded in the KB below.
   If the KB doesn't cover it, say "I'll confirm the specifics on our call"
   rather than guessing.
2. Pivot to booking a 15-minute call: {booking_url}
3. End with a one-line CTA that ties the call to their specific finding if
   one is given in the context.

Constraints: plain text, under 120 words, no subject/greeting/signature
block. Sign off "— Hammad".

Knowledge base (authoritative):
---
{kb}
---
"""

_OBJECTION_PROMPTS: dict[str, str] = {
    "price": (
        "The prospect raised a price / budget objection.\n\n"
        "Respond by briefly acknowledging the concern, then reframe:\n"
        " - average Canadian healthcare breach cost (~$6.94M, ~$950/record)\n"
        " - ransom demands on small clinics run $180k-$450k\n"
        " - HAWK Core at $299/mo is roughly the cost of 10 patient-record losses\n"
        "Then offer to show the actual vulnerabilities we found on their domain\n"
        "on a 15-min call. Use the booking link: {booking_url}.\n"
        "Keep under 110 words, plain text, sign off '— Hammad'."
    ),
    "have_provider": (
        "The prospect said they already have a provider/MSP.\n\n"
        "Respond by asking (one concrete question) what they're running today,\n"
        "then explain politely that most MSPs cover devices + backups but\n"
        "don't continuously scan the public attack surface for PIPEDA-relevant\n"
        "exposures. Position HAWK as a complement, not a replacement. Offer\n"
        "a 15-min call ({booking_url}) to walk through what's exposed that\n"
        "their current setup isn't catching. Do NOT name-disparage the\n"
        "current provider. Keep under 110 words, plain text, sign off '— Hammad'."
    ),
    "too_busy": (
        "The prospect said they're too busy right now.\n\n"
        "Respond by offering a 10-minute call instead of 15 and emphasising\n"
        "that onboarding is zero-effort on their end — we run the scan, send\n"
        "the report, they only show up. Drop the booking link: {booking_url}\n"
        "and offer to email them the three highest-severity findings for\n"
        "their domain in advance if that's more useful than a call. Keep\n"
        "under 100 words, plain text, sign off '— Hammad'."
    ),
    "not_interested": (
        "The prospect said they're not interested right now.\n\n"
        "Respond briefly: thank them for the reply, acknowledge the timing\n"
        "isn't right, and ask 'would a quick check-in in 90 days make sense,\n"
        "or would you rather we leave it?'. Do NOT push. Do not include the\n"
        "booking link. Keep under 60 words, plain text, sign off '— Hammad'."
    ),
}


def _classify_objection(reply_body: str) -> str:
    """Map a free-form objection reply to one of the four playbook keys."""
    text = (reply_body or "").lower()
    if any(
        term in text
        for term in (
            "expensive", "budget", "cost", "price", "pricing", "afford",
            "out of our range", "too much", "$",
        )
    ):
        return "price"
    if any(
        term in text
        for term in (
            "already have", "already use", "already working", "our msp",
            "our it", "our provider", "have a provider", "current provider",
            "covered by",
        )
    ):
        return "have_provider"
    if any(
        term in text
        for term in ("too busy", "no time", "swamped", "crazy week", "overloaded", "later")
    ):
        return "too_busy"
    return "not_interested"


def _draft_positive(context: str, kb_snippets: list[str]) -> str:
    kb_text = "\n\n".join(kb_snippets) if kb_snippets else aria_knowledge_base.get_full_kb()
    system = _POSITIVE_SYSTEM.format(booking_url=_booking_url(), kb=kb_text[:9000])
    return chat_text_sync(
        api_key=OPENAI_API_KEY,
        user_messages=[{"role": "user", "content": context}],
        max_tokens=320,
        system=system,
        model=OPENAI_MODEL,
    ).strip()


def _draft_question(context: str, kb_snippets: list[str]) -> str:
    kb_text = "\n\n".join(kb_snippets) if kb_snippets else aria_knowledge_base.get_full_kb()
    system = _QUESTION_SYSTEM.format(booking_url=_booking_url(), kb=kb_text[:9000])
    return chat_text_sync(
        api_key=OPENAI_API_KEY,
        user_messages=[{"role": "user", "content": context}],
        max_tokens=400,
        system=system,
        model=OPENAI_MODEL,
    ).strip()


def _draft_objection(context: str, playbook: str) -> str:
    system = _OBJECTION_PROMPTS[playbook].format(booking_url=_booking_url())
    return chat_text_sync(
        api_key=OPENAI_API_KEY,
        user_messages=[{"role": "user", "content": context}],
        max_tokens=320,
        system=system,
        model=OPENAI_MODEL,
    ).strip()


# ── Outbound send ─────────────────────────────────────────────────────────


def _build_subject(prior_subject: str) -> str:
    prior = (prior_subject or "").strip()
    if not prior:
        return "Re: your note"
    if prior.lower().startswith("re:"):
        return prior[:180]
    return f"Re: {prior}"[:180]


def _send_via_mailbox(
    *,
    prospect: dict[str, Any],
    subject: str,
    body_text: str,
) -> dict[str, Any]:
    """Pick a mailbox + send via PR #35's SMTP dispatcher.

    Threading: the mailbox sender generates a fresh RFC 5322 ``Message-ID`` so
    *this* reply becomes its own thread anchor on our side. Gmail/Outlook still
    collapse it into the prospect's original thread because subject starts
    with ``Re:`` — that's the convention Apple/Outlook/Gmail all honour.
    """
    vertical = (prospect.get("vertical") or "").strip() or "unknown"
    mailbox = pick_next_for_vertical(vertical)
    if not mailbox:
        raise RuntimeError("no mailbox available for auto-reply")

    html_body = "".join(
        f"<p>{p}</p>" for p in body_text.replace("\r", "").split("\n\n") if p.strip()
    )
    contact_email = (prospect.get("contact_email") or "").strip()
    contact_name = " ".join(
        p for p in (prospect.get("first_name"), prospect.get("last_name")) if p
    ).strip() or contact_email.split("@")[0]

    result = send_via_mailbox(
        str(mailbox["id"]),
        to_email=contact_email,
        to_name=contact_name,
        subject=subject,
        body_text=body_text,
        body_html=html_body,
    )
    if not getattr(result, "ok", False):
        raise RuntimeError(getattr(result, "error", None) or "smtp send failed")
    return {
        "mailbox_id": str(mailbox["id"]),
        "message_id": getattr(result, "message_id", None),
    }


def _fetch_prospect(email: str) -> dict[str, Any] | None:
    if not SUPABASE_URL or not email:
        return None
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "contact_email": f"eq.{email.lower().strip()}",
                "select": "id,contact_email,first_name,last_name,company_name,domain,vertical,sent_message_id,assigned_rep_id,hawk_score",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception:
        logger.exception("aria_auto_reply: prospect lookup failed email=%s", email)
        return None


def _patch_inbound_reply(reply_id: str, **fields: Any) -> None:
    if not SUPABASE_URL or not reply_id:
        return
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
            headers=_sb_headers(),
            params={"id": f"eq.{reply_id}"},
            json=fields,
            timeout=15.0,
        ).raise_for_status()
    except Exception:
        logger.exception("_patch_inbound_reply failed id=%s", reply_id)


def _patch_prospect(prospect_id: str, **fields: Any) -> None:
    if not SUPABASE_URL or not prospect_id:
        return
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json=fields,
            timeout=15.0,
        ).raise_for_status()
    except Exception:
        logger.exception("_patch_prospect failed id=%s", prospect_id)


def _alert_human_checkpoint(*, prospect: dict[str, Any], reply_id: str, reason: str) -> None:
    base = (CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com").rstrip("/")
    company = prospect.get("company_name") or prospect.get("domain") or "prospect"
    link = f"{base}/crm/prospects/{prospect.get('id')}"
    msg = (
        f"HAWK — HUMAN CHECKPOINT\n"
        f"{company} ({prospect.get('contact_email')})\n"
        f"Reason: {reason}\n"
        f"Reply: {link}"
    )[:1500]
    try:
        send_ceo_sms(msg)
    except Exception:
        logger.exception("human checkpoint CEO SMS failed")
    kevin = (os.environ.get("KEVIN_SMS_NUMBER", "").strip()
             or aria_settings.get_setting("kevin_sms_number", ""))
    if kevin:
        try:
            send_sms(kevin, msg)
        except Exception:
            logger.exception("human checkpoint Kevin SMS failed")


# ── Public entrypoint ─────────────────────────────────────────────────────


def handle_reply(
    *,
    reply_id: str,
    sentiment: str,
    prospect_email: str,
    reply_subject: str,
    reply_body: str,
    vulnerability: str | None,
    company_name: str | None,
) -> dict[str, Any]:
    """Main hook called by ``aria_reply_handler.process_reply_event``.

    Returns a status dict; ``{"status": "auto_sent" | "queued_for_va" |
    "scheduled_followup" | "suppressed" | "human_checkpoint"}``.
    """
    # Kill-switch.
    if not autonomous_reply_enabled():
        return {"status": "queued_for_va", "reason": "autonomous_reply_disabled"}

    # Lookups we need either way.
    prospect = _fetch_prospect(prospect_email) or {}
    prospect_id = str(prospect.get("id") or "") or None
    vertical = prospect.get("vertical")

    # Human checkpoint — legal / enterprise / high-value.
    checkpoint = aria_human_checkpoint.evaluate(reply_body, reply_subject)
    if checkpoint.trip:
        _patch_inbound_reply(
            reply_id,
            status="needs_human",
            checkpoint_reason=checkpoint.reason,
        )
        if prospect_id:
            _alert_human_checkpoint(prospect=prospect, reply_id=reply_id, reason=checkpoint.reason)
        return {"status": "human_checkpoint", "reason": checkpoint.reason}

    # Unsubscribe — suppress + stop, no reply.
    if sentiment == "unsubscribe":
        _patch_inbound_reply(reply_id, status="auto_handled")
        if prospect_id:
            aria_scheduled_actions.cancel_pending(prospect_id)
            _patch_prospect(
                prospect_id,
                stage="unsubscribed",
                pipeline_status="suppressed",
                nurture_stopped_at=datetime.now(timezone.utc).isoformat(),
                nurture_stopped_reason="unsubscribe",
            )
        return {"status": "suppressed", "reason": "unsubscribe"}

    # Out of office — parse return date + schedule follow-up.
    if sentiment == "out_of_office":
        return_date = aria_ooo_parser.extract_return_date(reply_body)
        if not return_date:
            return_date = aria_ooo_parser.default_followup_date()
        due = datetime.combine(return_date, datetime.min.time(), tzinfo=timezone.utc).replace(hour=15)
        if prospect_id:
            aria_scheduled_actions.schedule(
                action_type="ooo_return_followup",
                due_at=due,
                prospect_id=prospect_id,
                inbound_reply_id=reply_id,
                payload={
                    "return_date": return_date.isoformat(),
                    "reason": "ooo",
                },
            )
        _patch_inbound_reply(reply_id, status="auto_handled")
        return {"status": "scheduled_followup", "reason": "ooo", "due_at": due.isoformat()}

    # Only auto-send when we have everything we need to actually send.
    if not prospect_id or not prospect.get("contact_email"):
        _patch_inbound_reply(reply_id, status="classified")
        return {"status": "queued_for_va", "reason": "no_prospect_match"}
    if not OPENAI_API_KEY:
        _patch_inbound_reply(reply_id, status="classified")
        return {"status": "queued_for_va", "reason": "no_openai_key"}

    first_name = prospect.get("first_name") or None
    last_name = prospect.get("last_name") or None
    prospect_name = " ".join(p for p in (first_name, last_name) if p).strip() or None
    context = _build_context(
        prospect_name=prospect_name,
        company_name=company_name or prospect.get("company_name"),
        vertical=vertical,
        vulnerability=vulnerability,
        reply_subject=reply_subject,
        reply_body=reply_body,
    )

    draft_body: str
    playbook: str | None = None
    kb_snippets_used = 0

    if sentiment == "positive":
        kb_snippets = aria_knowledge_base.retrieve_snippets(reply_body, max_sections=3)
        kb_snippets_used = len(kb_snippets)
        draft_body = _draft_positive(context, kb_snippets)
    elif sentiment == "question":
        kb_snippets = aria_knowledge_base.retrieve_snippets(reply_body, max_sections=4)
        kb_snippets_used = len(kb_snippets)
        draft_body = _draft_question(context, kb_snippets)
    elif sentiment == "objection":
        playbook = _classify_objection(reply_body)
        draft_body = _draft_objection(context, playbook)
    else:
        # 'not_interested' / 'other' — route to VA queue, no auto-send.
        _patch_inbound_reply(reply_id, status="classified")
        return {"status": "queued_for_va", "reason": sentiment}

    if not draft_body:
        _patch_inbound_reply(reply_id, status="classified")
        return {"status": "queued_for_va", "reason": "empty_draft"}

    final_body = draft_body + _add_reply_quote(reply_body)
    subject = _build_subject(reply_subject)

    # Send via mailbox SMTP dispatcher.
    try:
        sent = _send_via_mailbox(
            prospect=prospect,
            subject=subject,
            body_text=final_body,
        )
    except Exception as exc:
        logger.exception("auto_reply send failed prospect=%s sentiment=%s", prospect_id, sentiment)
        _patch_inbound_reply(
            reply_id,
            status="classified",
            classification_reasoning=f"auto-send failed: {exc!s}"[:500],
        )
        return {"status": "queued_for_va", "reason": f"send_failed: {exc!s}"[:200]}

    now_iso = datetime.now(timezone.utc).isoformat()
    _patch_inbound_reply(
        reply_id,
        status="auto_handled",
        drafted_response_subject=subject,
        drafted_response_body=final_body,
        auto_sent_at=now_iso,
        auto_sent_mailbox_id=sent.get("mailbox_id"),
        auto_sent_message_id=sent.get("message_id"),
        objection_playbook=playbook,
        knowledge_base_snippets_used=kb_snippets_used,
    )
    _patch_prospect(
        prospect_id,
        last_auto_reply_at=now_iso,
        last_activity_at=now_iso,
    )

    # Schedule a 48h follow-up if they didn't ask a yes/no question and
    # haven't already booked. Only for positive/question flows — objections
    # have their own lighter-touch cadence handled elsewhere.
    if sentiment in ("positive", "question"):
        from services.aria_nurture import schedule_48h_followup
        schedule_48h_followup(prospect_id=prospect_id, reply_id=reply_id)

    # 90-day snooze hook — only fired when the objection was classified as
    # "not_interested". Kept here so the snooze is written even if the
    # original send fails (we should still honour "circle back later").
    if sentiment == "objection" and playbook == "not_interested":
        due = datetime.now(timezone.utc) + timedelta(days=90)
        aria_scheduled_actions.schedule(
            action_type="snooze_90d",
            due_at=due,
            prospect_id=prospect_id,
            inbound_reply_id=reply_id,
            payload={"reason": "not_interested_90d_snooze"},
        )

    return {
        "status": "auto_sent",
        "sentiment": sentiment,
        "playbook": playbook,
        "mailbox_id": sent.get("mailbox_id"),
        "message_id": sent.get("message_id"),
    }


__all__ = ["handle_reply", "autonomous_reply_enabled"]
