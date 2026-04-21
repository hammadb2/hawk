"""
ARIA Smartlead Reply Handler — processes inbound replies from the Smartlead webhook.

Classifies sentiment, drafts response, routes to aria_inbound_replies table.
Handles: reply, bounce, spam complaint events.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from config import CAL_COM_BOOKING_URL, OPENAI_API_KEY, OPENAI_MODEL, SUPABASE_URL
from services.openai_chat import chat_text_sync

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# ── Reply Classification ────────────────────────────────────────────────

CLASSIFICATION_SYSTEM_PROMPT = """You are ARIA, classifying inbound email replies for Hawk Security's outbound campaigns.

Classify the reply into exactly ONE of these categories:
- positive: interested in learning more, wants to book a call, asks about pricing
- objection: has concerns but not outright refusing (already has a provider, budget, timing)
- not_interested: clearly does not want to engage, asks to stop
- unsubscribe: explicitly says "stop", "unsubscribe", "remove me", "do not contact"
- out_of_office: auto-reply, OOO, vacation, parental leave
- question: asking a genuine question about the service or findings
- other: anything that doesn't fit above

Also provide:
1. A confidence score (0.0 to 1.0)
2. Brief reasoning (1 sentence)

Return ONLY valid JSON:
{"sentiment": "category", "confidence": 0.95, "reasoning": "one sentence explanation"}
"""

RESPONSE_SYSTEM_PROMPT = """You are ARIA, drafting a reply for HAWK Security, a US managed-
cybersecurity service for small US professional practices (dental, legal, CPA).

This prompt is only used as a last-resort fallback when the knowledge-base-grounded
drafter in ``aria_auto_reply`` can't run. The primary drafter owns tone, length,
and compliance framing; this fallback keeps the VA-queue preview reasonable.

Rules:
1. Match the tone of the prospect's message.
2. Keep it under 80 words.
3. No "Great question" / "Thanks for getting back to me" / "I hope this finds you well".
4. Be direct and specific.
5. For positive replies: propose a 15-minute call and include the booking link verbatim.
6. For objections: acknowledge the concern, offer one concrete value prop (Breach
   Response Guarantee by tier, or the HIPAA / FTC Safeguards / ABA Opinion 2024-3
   artifacts we produce). Never name-disparage their existing provider.
7. For questions: answer directly, offer to elaborate on a call.
8. Never be pushy or salesy. No bold claims.
9. Sign off as "— Hammad".

Booking link (must appear verbatim in positive / objection replies): {booking_url}

Return ONLY the email reply body text (no JSON, no subject line).
"""


def classify_reply(reply_body: str, reply_subject: str | None = None) -> dict[str, Any]:
    """Classify an inbound reply using OpenAI."""
    if not OPENAI_API_KEY:
        return {"sentiment": "other", "confidence": 0.0, "reasoning": "OpenAI not configured"}

    content = f"Subject: {reply_subject or '(none)'}\n\nBody:\n{reply_body[:2000]}"

    try:
        raw = chat_text_sync(
            api_key=OPENAI_API_KEY,
            user_messages=[{"role": "user", "content": content}],
            max_tokens=200,
            system=CLASSIFICATION_SYSTEM_PROMPT,
            model=OPENAI_MODEL,
        )

        # Parse JSON response
        text = raw.strip()
        if "```" in text:
            import re
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m:
                text = m.group(1).strip()

        result = json.loads(text)
        valid_sentiments = {"positive", "objection", "not_interested", "unsubscribe", "out_of_office", "question", "other"}
        sentiment = result.get("sentiment", "other")
        if sentiment not in valid_sentiments:
            sentiment = "other"

        return {
            "sentiment": sentiment,
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": str(result.get("reasoning", ""))[:500],
        }
    except Exception as exc:
        logger.warning("Reply classification failed: %s", exc)
        return {"sentiment": "other", "confidence": 0.0, "reasoning": f"Classification error: {exc!s}"[:200]}


def draft_response(
    reply_body: str,
    sentiment: str,
    prospect_name: str | None = None,
    company_name: str | None = None,
    vulnerability: str | None = None,
) -> dict[str, str]:
    """Draft a response to an inbound reply using OpenAI."""
    if not OPENAI_API_KEY:
        return {"subject": "", "body": ""}

    # Auto-handled categories don't need a draft
    if sentiment in ("out_of_office", "unsubscribe"):
        return {"subject": "", "body": ""}

    booking_url = CAL_COM_BOOKING_URL or "https://cal.com/hawksecurity/15min"
    system = RESPONSE_SYSTEM_PROMPT.format(booking_url=booking_url)

    context_parts = [f"Prospect reply:\n{reply_body[:1500]}"]
    if prospect_name:
        context_parts.append(f"Prospect name: {prospect_name}")
    if company_name:
        context_parts.append(f"Company: {company_name}")
    if vulnerability:
        context_parts.append(f"Finding from scan: {vulnerability}")
    context_parts.append(f"Sentiment: {sentiment}")

    try:
        body = chat_text_sync(
            api_key=OPENAI_API_KEY,
            user_messages=[{"role": "user", "content": "\n".join(context_parts)}],
            max_tokens=300,
            system=system,
            model=OPENAI_MODEL,
        )

        # Generate subject
        subject = f"Re: {prospect_name or 'your'} inquiry" if sentiment == "positive" else f"Re: Hawk Security follow up"

        return {"subject": subject, "body": body.strip()}
    except Exception as exc:
        logger.warning("Response draft failed: %s", exc)
        return {"subject": "", "body": ""}


# ── Webhook Event Processing ────────────────────────────────────────────

def process_reply_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Process a Smartlead reply webhook event.

    Expected event shape:
    {
        "event_type": "reply",
        "lead": {"email": "...", "first_name": "...", "last_name": "..."},
        "campaign_id": "...",
        "email": {"subject": "...", "body": "...", "text_body": "..."},
        ...
    }
    """
    lead_data = event.get("lead") or {}
    email_data = event.get("email") or {}
    campaign_id = str(event.get("campaign_id") or "")

    prospect_email = (lead_data.get("email") or "").strip().lower()
    prospect_name = f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip() or None
    prospect_domain = prospect_email.split("@")[-1] if "@" in prospect_email else ""

    reply_subject = email_data.get("subject") or ""
    reply_body = email_data.get("text_body") or email_data.get("body") or ""

    if not reply_body:
        return {"ok": False, "error": "No reply body in event"}

    # Classify
    classification = classify_reply(reply_body, reply_subject)
    sentiment = classification["sentiment"]

    # Look up inventory lead for context
    inventory_lead = _find_inventory_lead(prospect_email, prospect_domain)
    vulnerability = None
    company_name = None
    inventory_lead_id = None
    if inventory_lead:
        vulnerability = inventory_lead.get("vulnerability_found")
        company_name = inventory_lead.get("business_name")
        inventory_lead_id = inventory_lead.get("id")

    # We deliberately do NOT run ``draft_response`` here anymore. The KB-grounded
    # drafter in ``aria_auto_reply.handle_reply`` owns the real send, and the
    # generic draft we used to produce here was always thrown away by that path
    # — so it was a ~1-2s latency tax + duplicate OpenAI spend on every reply
    # that bit into the ≤5-minute autonomous-reply SLA without any benefit to
    # the recipient. ``draft_response`` is still exported for VA-queue paths
    # that want a cheap preview when auto-reply is disabled; the VA console
    # calls it on-demand when it needs one.
    draft = {"subject": "", "body": ""}

    # Determine initial status
    status = "classified"
    if sentiment == "out_of_office":
        status = "auto_handled"
    elif sentiment == "unsubscribe":
        status = "auto_handled"
        _add_to_suppressions(prospect_email, prospect_domain, "unsubscribe_reply")

    # Store in aria_inbound_replies
    row = {
        "smartlead_lead_id": str(lead_data.get("id") or ""),
        "smartlead_campaign_id": campaign_id,
        "prospect_email": prospect_email,
        "prospect_name": prospect_name,
        "prospect_domain": prospect_domain,
        "reply_subject": reply_subject[:500],
        "reply_body": reply_body[:5000],
        "reply_received_at": datetime.now(timezone.utc).isoformat(),
        "sentiment": sentiment,
        "confidence_score": classification["confidence"],
        "classification_reasoning": classification["reasoning"],
        "drafted_response_subject": draft.get("subject"),
        "drafted_response_body": draft.get("body"),
        "status": status,
        "inventory_lead_id": inventory_lead_id,
        "webhook_payload": event,
    }

    reply_id = _store_reply(row)
    _patch_prospect_on_smartlead_reply(prospect_email, sentiment)

    # Hand off to the autonomous reply loop. This is where ARIA actually
    # *sends* the response (for positive / question / objection), parses
    # OOO return dates, schedules 48h follow-ups, and trips the human
    # checkpoint for legal / custom-contract / >$5k deals.
    auto_result: dict[str, Any] = {}
    if reply_id:
        try:
            from services import aria_auto_reply

            auto_result = aria_auto_reply.handle_reply(
                reply_id=reply_id,
                sentiment=sentiment,
                prospect_email=prospect_email,
                reply_subject=reply_subject,
                reply_body=reply_body,
                vulnerability=vulnerability,
                company_name=company_name,
            ) or {}
        except Exception as exc:
            logger.exception("auto_reply dispatch failed reply=%s", reply_id)
            auto_result = {"status": "queued_for_va", "reason": f"dispatch_error: {exc!s}"[:200]}

    return {
        "ok": True,
        "reply_id": reply_id,
        "sentiment": sentiment,
        "confidence": classification["confidence"],
        "status": auto_result.get("status") or status,
        "auto_reply": auto_result,
    }


def _extract_sending_domain(event: dict[str, Any]) -> str:
    """Extract the sending (from) domain from a Smartlead webhook event.

    Smartlead may provide the sending email in various fields depending on
    webhook version. We try several common field names and fall back to empty.
    """
    for key in ("from_email", "email_account", "sender_email", "from"):
        val = event.get(key)
        if isinstance(val, str) and "@" in val:
            return val.strip().lower().split("@")[-1]
    # Some payloads nest it under email_account_id or account
    account = event.get("email_account") or event.get("account") or {}
    if isinstance(account, dict):
        for key in ("email", "from_email", "sender_email"):
            val = account.get(key)
            if isinstance(val, str) and "@" in val:
                return val.strip().lower().split("@")[-1]
    return ""


def process_bounce_event(event: dict[str, Any]) -> dict[str, Any]:
    """Process a Smartlead bounce webhook event."""
    lead_data = event.get("lead") or {}
    email = (lead_data.get("email") or "").strip().lower()
    domain = email.split("@")[-1] if "@" in email else ""

    if email:
        _add_to_suppressions(email, domain, "bounce")
        _suppress_inventory_lead(email, "bounce")

    # Update sending domain health metrics (not prospect domain)
    sending_domain = _extract_sending_domain(event)
    if sending_domain:
        _increment_domain_bounce(sending_domain)

    return {"ok": True, "event": "bounce", "email": email, "sending_domain": sending_domain}


def process_spam_complaint_event(event: dict[str, Any]) -> dict[str, Any]:
    """Process a Smartlead spam complaint webhook event."""
    lead_data = event.get("lead") or {}
    email = (lead_data.get("email") or "").strip().lower()
    domain = email.split("@")[-1] if "@" in email else ""

    if email:
        _add_to_suppressions(email, domain, "spam_complaint")
        _suppress_inventory_lead(email, "spam_complaint")

    # Update sending domain health metrics (not prospect domain)
    sending_domain = _extract_sending_domain(event)
    if sending_domain:
        _increment_domain_spam(sending_domain)

    return {"ok": True, "event": "spam_complaint", "email": email, "sending_domain": sending_domain}


# ── Database Helpers ────────────────────────────────────────────────────

def _find_inventory_lead(email: str, domain: str) -> dict[str, Any] | None:
    """Find lead in aria_lead_inventory by email or domain."""
    if not SUPABASE_URL or (not email and not domain):
        return None

    headers = _sb_headers()

    if email:
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
                headers=headers,
                params={"contact_email": f"eq.{email}", "select": "*", "limit": "1"},
                timeout=15.0,
            )
            if r.status_code < 300 and r.json():
                return r.json()[0]
        except Exception:
            pass

    if domain:
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
                headers=headers,
                params={"domain": f"eq.{domain}", "select": "*", "limit": "1"},
                timeout=15.0,
            )
            if r.status_code < 300 and r.json():
                return r.json()[0]
        except Exception:
            pass

    return None


def _patch_prospect_on_smartlead_reply(prospect_email: str, sentiment: str) -> None:
    """Set reply_received_at; positive replies → is_hot + stage=replied."""
    if not SUPABASE_URL or not SERVICE_KEY or not prospect_email:
        return
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"contact_email": f"eq.{prospect_email.strip().lower()}", "select": "id", "limit": "1"},
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return
        pid = str(rows[0]["id"])
        patch: dict[str, Any] = {"reply_received_at": datetime.now(timezone.utc).isoformat()}
        if sentiment == "positive":
            patch["is_hot"] = True
            patch["stage"] = "replied"
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{pid}"},
            json=patch,
            timeout=15.0,
        ).raise_for_status()
    except Exception as exc:
        logger.warning("Prospect patch on Smartlead reply failed for %s: %s", prospect_email, exc)


def _store_reply(row: dict[str, Any]) -> str | None:
    """Insert reply into aria_inbound_replies. Returns reply ID."""
    if not SUPABASE_URL:
        return None

    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
            headers=_sb_headers(),
            json=row,
            timeout=20.0,
        )
        if r.status_code < 300:
            data = r.json()
            if isinstance(data, list) and data:
                return str(data[0].get("id", ""))
            if isinstance(data, dict):
                return str(data.get("id", ""))
        else:
            logger.error("Failed to store reply: %s", r.text[:500])
    except Exception as exc:
        logger.exception("Reply store failed: %s", exc)

    return None


def _add_to_suppressions(email: str, domain: str, reason: str) -> None:
    """Add email/domain to suppressions table."""
    if not SUPABASE_URL:
        return

    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/suppressions",
            headers=_sb_headers(),
            json={
                "email": email,
                "domain": domain,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("Failed to add suppression for %s: %s", email, exc)


def _suppress_inventory_lead(email: str, reason: str) -> None:
    """Mark lead as suppressed in aria_lead_inventory."""
    if not SUPABASE_URL or not email:
        return

    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/aria_lead_inventory",
            headers=_sb_headers(),
            params={"contact_email": f"eq.{email}"},
            json={
                "status": "suppressed",
                "suppression_reason": reason,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("Failed to suppress inventory lead %s: %s", email, exc)


def _upsert_domain_health_increment(domain: str, field: str) -> None:
    """Atomically increment a counter in aria_domain_health using upsert.

    If the domain row doesn't exist yet, creates it with the counter set to 1.
    Uses PostgREST upsert (ON CONFLICT) to avoid race conditions between
    concurrent webhook calls for the same domain.
    """
    if not SUPABASE_URL or not domain:
        return

    now = datetime.now(timezone.utc).isoformat()
    headers = {**_sb_headers(), "Prefer": "return=representation,resolution=merge-duplicates"}

    try:
        # First try: read current value + patch (works for existing rows)
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_domain_health",
            headers=_sb_headers(),
            params={"domain": f"eq.{domain}", "select": f"id,{field}", "limit": "1"},
            timeout=15.0,
        )
        if r.status_code < 300 and r.json():
            current = int(r.json()[0].get(field) or 0)
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/aria_domain_health",
                headers=_sb_headers(),
                params={"domain": f"eq.{domain}"},
                json={field: current + 1, "updated_at": now},
                timeout=15.0,
            )
        else:
            # Row doesn't exist — upsert to create it with counter = 1
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_domain_health",
                headers=headers,
                json={
                    "domain": domain,
                    field: 1,
                    "sends_7d": 0,
                    "bounces_7d": 0,
                    "spam_complaints_7d": 0,
                    "replies_7d": 0,
                    "status": "healthy",
                    "updated_at": now,
                },
                timeout=15.0,
            )
    except Exception as exc:
        logger.warning("Failed to increment %s for %s: %s", field, domain, exc)


def _increment_domain_bounce(domain: str) -> None:
    """Increment bounce count in aria_domain_health."""
    _upsert_domain_health_increment(domain, "bounces_7d")


def _increment_domain_spam(domain: str) -> None:
    """Increment spam complaint count in aria_domain_health."""
    _upsert_domain_health_increment(domain, "spam_complaints_7d")
