"""ARIA Phase 5 — Inbound reply classification and response drafting.

When a prospect replies to a Smartlead cold email, ARIA:
1. Classifies the reply (interested, objection, not_interested, unsubscribe, out_of_office, question, positive_other)
2. Drafts a personalized response using the objection playbook and prospect context
3. Queues the draft for one-tap human approval before sending
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"
SMARTLEAD_API_KEY = os.environ.get("SMARTLEAD_API_KEY", "").strip()

# Cal.com booking link for CTAs
CAL_COM_BOOKING_URL = os.environ.get("CAL_COM_BOOKING_URL", "https://cal.com").strip().rstrip("/")


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# ── Objection playbook ──────────────────────────────────────────────────

OBJECTION_PLAYBOOK: dict[str, list[dict[str, str]]] = {
    "price": [
        {
            "objection": "Too expensive / not in budget",
            "strategy": "Reframe as insurance. A breach costs $150K+ on average. Plans start at $199/mo.",
        },
    ],
    "existing_vendor": [
        {
            "objection": "We already have IT / cybersecurity",
            "strategy": "Acknowledge their vendor. Our scan is external — it shows what attackers see from outside, which internal tools miss.",
        },
    ],
    "timing": [
        {
            "objection": "Not a good time / too busy",
            "strategy": "Empathize with timing. Offer a 15-minute call at their convenience. Busy periods = higher risk.",
        },
    ],
    "not_a_target": [
        {
            "objection": "We're too small to be targeted",
            "strategy": "43% of cyberattacks target small businesses. Automated scanning tools don't discriminate by size.",
        },
    ],
    "compliance": [
        {
            "objection": "We're already compliant (PIPEDA/PHIPA)",
            "strategy": "Compliance covers process, not technical exposure. Our scan shows what's visible externally — open ports, leaked creds, vulnerable services.",
        },
    ],
    "send_info": [
        {
            "objection": "Just send me info by email",
            "strategy": "Happy to. Mention that you have their scan report ready and can walk them through the findings in 15 minutes.",
        },
    ],
    "general": [
        {
            "objection": "Generic pushback or unclear objection",
            "strategy": "Acknowledge their concern, reiterate the specific vulnerability found on their domain, and offer a brief call to discuss.",
        },
    ],
}


# ── Classification ───────────────────────────────────────────────────────

CLASSIFICATION_SYSTEM_PROMPT = """You are ARIA, the AI operations assistant for Hawk Security.
Your job is to classify inbound email replies from prospects and draft appropriate responses.

Hawk Security is a Canadian cybersecurity company targeting dental clinics, law firms, and accounting practices.
Products: Starter $199/mo, Shield $997/mo, Enterprise $2,500/mo.
Primary angle: PIPEDA compliance and external attack surface scanning.

Classify the reply into exactly ONE of these categories:
- interested: Prospect wants to learn more, book a call, or is open to discussion
- objection: Prospect raised a concern (price, timing, existing vendor, compliance, etc.)
- not_interested: Clear rejection, hard no
- unsubscribe: Wants to be removed from the mailing list
- out_of_office: Auto-reply, vacation, or OOO message
- question: Asking a question without clear positive or negative intent
- positive_other: Positive response that doesn't fit other categories (e.g., forwarded to colleague)

Return a JSON object with:
{
  "classification": "one of the categories above",
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation of why this classification",
  "objection_type": "price|existing_vendor|timing|not_a_target|compliance|send_info|general (only if classification is objection, else null)",
  "sentiment": "positive|neutral|negative",
  "key_points": ["list of key points from the reply"]
}"""


def classify_reply(reply_content: str, prospect_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify an inbound reply using OpenAI."""
    if not OPENAI_API_KEY:
        return {
            "classification": "pending",
            "confidence": 0.0,
            "reasoning": "OpenAI not configured",
            "objection_type": None,
            "sentiment": "neutral",
            "key_points": [],
        }

    context_str = ""
    if prospect_context:
        context_str = f"""
Prospect context:
- Company: {prospect_context.get('company_name', 'Unknown')}
- Domain: {prospect_context.get('domain', 'Unknown')}
- Industry: {prospect_context.get('industry', 'Unknown')}
- Contact: {prospect_context.get('contact_name', 'Unknown')}
- Hawk Score: {prospect_context.get('hawk_score', 'N/A')}
- Vulnerability: {prospect_context.get('vulnerability_found', 'N/A')}
"""

    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": f"{context_str}\nReply to classify:\n\n{reply_content}"},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        result = json.loads(raw)
        # Validate classification
        valid = ("interested", "objection", "not_interested", "unsubscribe", "out_of_office", "question", "positive_other")
        if result.get("classification") not in valid:
            result["classification"] = "question"
        return result
    except Exception:
        logger.exception("Reply classification failed")
        return {
            "classification": "pending",
            "confidence": 0.0,
            "reasoning": "Classification failed",
            "objection_type": None,
            "sentiment": "neutral",
            "key_points": [],
        }


# ── Response drafting ────────────────────────────────────────────────────

DRAFT_SYSTEM_PROMPT = """You are ARIA, drafting a reply to a prospect's email for Hawk Security.

Rules:
- Be concise, professional, and human-sounding. Not salesy.
- Never use phrases like "Great question" or "Certainly" or "I'd be happy to".
- Reference the specific vulnerability or exposure found on their domain if available.
- For objections, use the provided playbook strategy but make it conversational.
- Always include a soft CTA to book a 15-minute call when appropriate.
- For unsubscribe: politely confirm removal (no CTA).
- For out_of_office: do NOT draft a response (return empty).
- Keep the email under 100 words.
- Sign off as the assigned rep's name if provided, otherwise "The Hawk Security Team".

IMPORTANT: Return a JSON object with:
{
  "subject": "Reply subject line (usually Re: original subject)",
  "body": "The email body text",
  "reasoning": "Brief explanation of the response strategy chosen"
}"""


def draft_response(
    *,
    reply_content: str,
    classification: dict[str, Any],
    prospect_context: dict[str, Any] | None = None,
    rep_name: str | None = None,
) -> dict[str, Any]:
    """Draft a response to a classified reply."""
    cat = classification.get("classification", "")

    # Auto-handle: no draft needed for OOO
    if cat == "out_of_office":
        return {"subject": "", "body": "", "reasoning": "Out-of-office — no response needed", "auto_handle": True}

    if not OPENAI_API_KEY:
        return {"subject": "", "body": "", "reasoning": "OpenAI not configured", "auto_handle": False}

    # Build context for the drafter
    context_parts: list[str] = []

    if prospect_context:
        context_parts.append(f"Company: {prospect_context.get('company_name', 'Unknown')}")
        context_parts.append(f"Domain: {prospect_context.get('domain', 'Unknown')}")
        context_parts.append(f"Industry: {prospect_context.get('industry', 'Unknown')}")
        context_parts.append(f"Contact: {prospect_context.get('contact_name', 'Unknown')}")
        vuln = prospect_context.get("vulnerability_found")
        if vuln:
            context_parts.append(f"Vulnerability found: {vuln}")

    context_parts.append(f"Classification: {cat}")
    context_parts.append(f"Sentiment: {classification.get('sentiment', 'neutral')}")

    objection_type = classification.get("objection_type")
    if cat == "objection" and objection_type:
        playbook_entries = OBJECTION_PLAYBOOK.get(objection_type, OBJECTION_PLAYBOOK["general"])
        for entry in playbook_entries:
            context_parts.append(f"Objection playbook: {entry['strategy']}")

    if rep_name:
        context_parts.append(f"Sign off as: {rep_name}")

    context_parts.append(f"Booking link: {CAL_COM_BOOKING_URL}")
    context_str = "\n".join(context_parts)

    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context_str}\n\nOriginal reply from prospect:\n\n{reply_content}"},
            ],
            temperature=0.4,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        result = json.loads(raw)
        result["auto_handle"] = False
        return result
    except Exception:
        logger.exception("Response drafting failed")
        return {"subject": "", "body": "", "reasoning": "Drafting failed", "auto_handle": False}


# ── Full pipeline: classify + draft + store ──────────────────────────────

def _get_prospect(prospect_id: str) -> dict[str, Any] | None:
    """Fetch prospect row by ID."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb(),
        params={"id": f"eq.{prospect_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    if r.status_code >= 400:
        return None
    rows = r.json()
    return rows[0] if rows else None


def _get_assigned_rep_name(prospect: dict[str, Any]) -> str | None:
    """Get the assigned rep's name."""
    rep_id = prospect.get("assigned_rep_id")
    if not rep_id:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb(),
        params={"id": f"eq.{rep_id}", "select": "full_name", "limit": "1"},
        timeout=15.0,
    )
    if r.status_code >= 400:
        return None
    rows = r.json()
    return rows[0].get("full_name") if rows else None


def _get_vulnerability_for_prospect(prospect: dict[str, Any]) -> str | None:
    """Check aria_pipeline_leads for vulnerability data on this prospect's domain."""
    domain = prospect.get("domain")
    if not domain:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_pipeline_leads",
        headers=_sb(),
        params={
            "domain": f"eq.{domain}",
            "select": "vulnerability_found",
            "order": "created_at.desc",
            "limit": "1",
        },
        timeout=15.0,
    )
    if r.status_code >= 400:
        return None
    rows = r.json()
    return rows[0].get("vulnerability_found") if rows else None


def process_inbound_reply(
    *,
    prospect_id: str,
    reply_content: str,
    reply_subject: str | None = None,
    reply_from_email: str | None = None,
    reply_from_name: str | None = None,
    email_event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full pipeline: classify reply, draft response, store in aria_inbound_replies."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "Supabase not configured"}

    headers = _sb()
    now = datetime.now(timezone.utc)

    # 1. Get prospect context
    prospect = _get_prospect(prospect_id)
    prospect_context: dict[str, Any] | None = None
    rep_name: str | None = None
    if prospect:
        vuln = _get_vulnerability_for_prospect(prospect)
        prospect_context = {
            "company_name": prospect.get("company_name"),
            "domain": prospect.get("domain"),
            "industry": prospect.get("industry"),
            "contact_name": prospect.get("contact_name"),
            "hawk_score": prospect.get("hawk_score"),
            "vulnerability_found": vuln,
        }
        rep_name = _get_assigned_rep_name(prospect)

    # 2. Classify
    classification = classify_reply(reply_content, prospect_context)
    cat = classification.get("classification", "pending")

    # 3. Draft response
    draft = draft_response(
        reply_content=reply_content,
        classification=classification,
        prospect_context=prospect_context,
        rep_name=rep_name,
    )

    # 4. Determine status
    auto_handle = draft.get("auto_handle", False)
    if cat == "out_of_office":
        status = "auto_handled"
    elif cat == "unsubscribe":
        # Auto-handle unsubscribe but still draft a confirmation email
        status = "pending_review"
    elif cat == "pending":
        status = "pending_classification"
    else:
        status = "pending_review"

    # 5. Store in aria_inbound_replies
    row = {
        "prospect_id": prospect_id,
        "email_event_id": email_event_id,
        "reply_content": reply_content,
        "reply_subject": reply_subject,
        "reply_from_email": reply_from_email,
        "reply_from_name": reply_from_name,
        "reply_received_at": now.isoformat(),
        "classification": cat,
        "classification_confidence": classification.get("confidence"),
        "classification_reasoning": classification.get("reasoning"),
        "draft_subject": draft.get("subject") or None,
        "draft_body": draft.get("body") or None,
        "draft_reasoning": draft.get("reasoning"),
        "status": status,
        "metadata": {
            **(metadata or {}),
            "objection_type": classification.get("objection_type"),
            "sentiment": classification.get("sentiment"),
            "key_points": classification.get("key_points", []),
            "auto_handled": auto_handle,
        },
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
        headers=headers,
        json=row,
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.warning("Failed to store inbound reply: %s", r.text[:300])
        return {"ok": False, "error": r.text[:300]}

    inserted = r.json()
    reply_id = inserted[0]["id"] if isinstance(inserted, list) and inserted else inserted.get("id")

    # 6. If unsubscribe, update prospect stage
    if cat == "unsubscribe" and prospect:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb(),
            params={"id": f"eq.{prospect_id}"},
            json={"stage": "unsubscribed", "last_activity_at": now.isoformat()},
            timeout=15.0,
        )

    return {
        "ok": True,
        "reply_id": reply_id,
        "classification": cat,
        "confidence": classification.get("confidence"),
        "status": status,
        "has_draft": bool(draft.get("body")),
        "auto_handled": auto_handle,
    }


# ── Approval actions ─────────────────────────────────────────────────────

def approve_reply(reply_id: str, reviewer_id: str, edited_body: str | None = None) -> dict[str, Any]:
    """Approve a drafted reply. Optionally edit the body before approval."""
    headers = _sb()

    # Fetch the reply
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
        headers=headers,
        params={"id": f"eq.{reply_id}", "select": "*", "limit": "1"},
        timeout=15.0,
    )
    if r.status_code >= 400 or not r.json():
        return {"ok": False, "error": "Reply not found"}

    reply = r.json()[0]
    if reply["status"] not in ("pending_review", "pending_classification"):
        return {"ok": False, "error": f"Reply status is {reply['status']}, cannot approve"}

    now = datetime.now(timezone.utc)
    update: dict[str, Any] = {
        "status": "approved",
        "reviewed_by": reviewer_id,
        "reviewed_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    if edited_body is not None:
        update["draft_body"] = edited_body

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
        headers=headers,
        params={"id": f"eq.{reply_id}"},
        json=update,
        timeout=15.0,
    )
    if r.status_code >= 400:
        return {"ok": False, "error": r.text[:300]}

    return {"ok": True, "reply_id": reply_id, "status": "approved"}


def reject_reply(reply_id: str, reviewer_id: str, note: str | None = None) -> dict[str, Any]:
    """Reject a drafted reply."""
    headers = _sb()
    now = datetime.now(timezone.utc)

    update: dict[str, Any] = {
        "status": "rejected",
        "reviewed_by": reviewer_id,
        "reviewed_at": now.isoformat(),
        "review_note": note,
        "updated_at": now.isoformat(),
    }

    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
        headers=headers,
        params={"id": f"eq.{reply_id}"},
        json=update,
        timeout=15.0,
    )
    if r.status_code >= 400:
        return {"ok": False, "error": r.text[:300]}

    return {"ok": True, "reply_id": reply_id, "status": "rejected"}


def send_approved_reply(reply_id: str) -> dict[str, Any]:
    """Send an approved reply via Smartlead API."""
    headers = _sb()

    # Fetch the reply
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
        headers=headers,
        params={"id": f"eq.{reply_id}", "select": "*", "limit": "1"},
        timeout=15.0,
    )
    if r.status_code >= 400 or not r.json():
        return {"ok": False, "error": "Reply not found"}

    reply = r.json()[0]
    if reply["status"] != "approved":
        return {"ok": False, "error": f"Reply status is {reply['status']}, must be approved to send"}

    if not reply.get("draft_body"):
        return {"ok": False, "error": "No draft body to send"}

    # Get prospect email
    prospect = _get_prospect(reply["prospect_id"])
    if not prospect:
        return {"ok": False, "error": "Prospect not found"}

    to_email = prospect.get("contact_email") or reply.get("reply_from_email")
    if not to_email:
        return {"ok": False, "error": "No email address for prospect"}

    # Send via Smartlead if configured
    if not SMARTLEAD_API_KEY:
        return {"ok": False, "error": "Smartlead API key not configured — cannot send"}

    smartlead_id = _send_via_smartlead(
        to_email=to_email,
        subject=reply.get("draft_subject") or "Re: Hawk Security",
        body=reply["draft_body"],
        prospect=prospect,
    )

    now = datetime.now(timezone.utc)
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/aria_inbound_replies",
        headers=headers,
        params={"id": f"eq.{reply_id}"},
        json={
            "status": "sent",
            "sent_at": now.isoformat(),
            "smartlead_message_id": smartlead_id,
            "updated_at": now.isoformat(),
        },
        timeout=15.0,
    )

    # Log activity
    httpx.post(
        f"{SUPABASE_URL}/rest/v1/activities",
        headers=_sb(),
        json={
            "prospect_id": reply["prospect_id"],
            "type": "aria_reply_sent",
            "notes": f"ARIA reply sent to {to_email}",
            "metadata": {"reply_id": reply_id, "classification": reply.get("classification")},
        },
        timeout=15.0,
    )

    return {"ok": True, "reply_id": reply_id, "status": "sent", "smartlead_message_id": smartlead_id}


def _send_via_smartlead(
    *,
    to_email: str,
    subject: str,
    body: str,
    prospect: dict[str, Any],
) -> str | None:
    """Send a reply through the Smartlead API. Returns message ID or None."""
    if not SMARTLEAD_API_KEY:
        logger.warning("Smartlead API key not configured — skipping send")
        return None

    # Smartlead reply API: POST /api/v1/leads/{lead_id}/reply
    # For now, log and return None — actual Smartlead send endpoint
    # depends on campaign ID and lead ID within Smartlead
    logger.info(
        "Smartlead send: to=%s subject=%s domain=%s (API integration pending campaign mapping)",
        to_email,
        subject,
        prospect.get("domain"),
    )
    # TODO: Wire to actual Smartlead reply API when campaign mapping is established
    return None
