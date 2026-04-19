"""CRM inbound webhooks — email engagement events (Smartlead / Charlotte / custom) into Supabase."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from config import CRM_PUBLIC_BASE_URL
from services.crm_openphone import (
    format_charlotte_reply_ceo_message,
    format_charlotte_reply_rep_message,
    send_ceo_sms,
    send_sms,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/webhooks", tags=["crm-webhooks"])

WEBHOOK_SECRET = os.environ.get("CRM_EMAIL_WEBHOOK_SECRET", "")
SMARTLEAD_WEBHOOK_SECRET = os.environ.get("CRM_SMARTLEAD_WEBHOOK_SECRET", "")
CAL_WEBHOOK_SECRET = os.environ.get("CAL_WEBHOOK_SECRET", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Charlotte / CEO alert — must be set via CRM_CEO_PHONE_E164 env var
CRM_CEO_PHONE_E164 = os.environ.get("CRM_CEO_PHONE_E164", "").strip()
VA_PHONE_NUMBER = os.environ.get("VA_PHONE_NUMBER", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def normalize_domain(raw: str) -> str:
    d = raw.strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix) :]
    d = d.split("/")[0].split("?")[0].strip()
    if not d:
        return ""
    if "@" in d:
        d = d.split("@")[-1]
    d = re.sub(r"^www\.", "", d)
    return d


class EmailEventIn(BaseModel):
    """Payload for POST /api/crm/webhooks/email-events — at least one of prospect_id, domain, or contact_email."""

    prospect_id: Optional[str] = None
    domain: Optional[str] = None
    contact_email: Optional[str] = Field(
        default=None,
        description="Prospect work email (used to derive domain and match CRM row)",
    )
    first_name: Optional[str] = None
    hawk_score: Optional[int] = None
    subject: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    sequence_step: Optional[int] = None
    source: str = Field(default="smartlead", description="smartlead | charlotte | webhook | manual")
    external_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    event_type: Optional[str] = Field(
        default=None,
        description="Optional: email_replied | email_opened (Charlotte / Smartlead)",
    )
    company_name: Optional[str] = None
    industry: Optional[str] = None
    sentiment: Optional[str] = Field(
        default=None,
        description="Optional reply sentiment (e.g. positive) for CRM prospect updates",
    )

    @field_validator("domain", mode="before")
    @classmethod
    def empty_domain_to_none(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @field_validator("prospect_id", mode="before")
    @classmethod
    def empty_pid_to_none(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


def _require_webhook_secret(x_secret: str | None) -> None:
    if not WEBHOOK_SECRET:
        logger.warning("CRM_EMAIL_WEBHOOK_SECRET not set — rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")
    if not x_secret or not secrets.compare_digest(x_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _round_robin_closer_rep_id() -> tuple[str | None, str | None, str | None]:
    """Next active closer (preferred) or sales_rep. Returns (rep_id, full_name, whatsapp_e164).

    Uses optimistic locking via last_assigned_at to reduce race conditions:
    we PATCH only the row whose last_assigned_at still matches what we read.
    If another request grabbed the same rep first, the PATCH returns 0 rows
    and we retry with the next candidate.
    """
    headers = _sb_headers()
    for role in ("closer", "sales_rep"):
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=headers,
            params={
                "role": f"eq.{role}",
                "status": "eq.active",
                "select": "id,full_name,whatsapp_number,last_assigned_at",
                "order": "last_assigned_at.asc.nullsfirst",
                "limit": "5",
            },
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            continue
        now_iso = datetime.now(timezone.utc).isoformat()
        for candidate in rows:
            rid = str(candidate["id"])
            name = str(candidate.get("full_name") or candidate.get("email") or "Rep")
            wa = candidate.get("whatsapp_number")
            old_ts = candidate.get("last_assigned_at")
            # Optimistic lock: only update if last_assigned_at hasn't changed
            match_params: dict[str, str] = {"id": f"eq.{rid}"}
            if old_ts:
                match_params["last_assigned_at"] = f"eq.{old_ts}"
            else:
                match_params["last_assigned_at"] = "is.null"
            patch = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/profiles",
                headers={**headers, "Prefer": "return=representation"},
                params=match_params,
                json={"last_assigned_at": now_iso},
                timeout=20.0,
            )
            patch.raise_for_status()
            patched = patch.json()
            if patched:
                return rid, name, (str(wa).strip() if wa else None)
            # Another request grabbed this rep — try next candidate
    return None, None, None


def _get_prospect_row(prospect_id: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={"id": f"eq.{prospect_id}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _fetch_prospect_by_domain(nd: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={
            "domain": f"eq.{nd}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _fetch_prospect_by_contact_email(email: str) -> dict[str, Any] | None:
    if not email or "@" not in email:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb_headers(),
        params={
            "contact_email": f"eq.{email.strip()}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _create_prospect_charlotte(
    *,
    nd: str,
    stage: str,
    assigned_rep_id: str,
    company: str,
    industry: str | None,
    contact_email: str | None,
    contact_name: str | None,
    hawk_score: int,
) -> dict[str, Any]:
    headers = _sb_headers()
    row: dict[str, Any] = {
        "domain": nd,
        "company_name": company,
        "industry": industry,
        "stage": stage,
        "source": "charlotte",
        "assigned_rep_id": assigned_rep_id,
        "hawk_score": hawk_score,
        "last_activity_at": datetime.now(timezone.utc).isoformat(),
    }
    if contact_email:
        row["contact_email"] = contact_email
    if contact_name:
        row["contact_name"] = contact_name
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/prospects", headers=headers, json=row, timeout=20.0)
    if r.status_code == 409:
        raise HTTPException(status_code=409, detail="Duplicate domain")
    r.raise_for_status()
    out = r.json()
    return out[0] if isinstance(out, list) and out else out


def _resolve_domain(body: EmailEventIn) -> str:
    if body.domain:
        return normalize_domain(body.domain)
    ce = body.contact_email or (body.metadata or {}).get("contact_email")
    if isinstance(ce, str) and "@" in ce:
        return normalize_domain(ce.split("@")[1])
    return ""


def _resolve_prospect_or_create(body: EmailEventIn) -> tuple[str, bool]:
    """Returns (prospect_id, created_new)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    headers = _sb_headers()

    if body.prospect_id:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=headers,
            params={"id": f"eq.{body.prospect_id}", "select": "id", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise HTTPException(status_code=404, detail="Prospect not found")
        return str(rows[0]["id"]), False

    nd = _resolve_domain(body)
    md = body.metadata or {}
    contact_email = body.contact_email or md.get("contact_email")
    if isinstance(contact_email, str):
        contact_email = contact_email.strip() or None

    prospect: dict[str, Any] | None = None
    if nd:
        prospect = _fetch_prospect_by_domain(nd)
    if not prospect and contact_email:
        prospect = _fetch_prospect_by_contact_email(contact_email)

    if prospect:
        return str(prospect["id"]), False

    et = (body.event_type or md.get("event_type") or "").lower()
    is_reply = body.replied_at is not None or et in ("email_replied", "reply", "replied")
    is_open = not is_reply and (
        body.opened_at is not None or et in ("email_opened", "open", "opened")
    )

    if not is_reply and not is_open:
        raise HTTPException(status_code=404, detail="No prospect for domain / email")

    if not nd:
        raise HTTPException(status_code=400, detail="Provide prospect_id, domain, or contact_email")

    rep_id, _rep_name, _rep_wa = _round_robin_closer_rep_id()
    if not rep_id:
        raise HTTPException(status_code=503, detail="No active closer or sales_rep for round-robin")

    stage = "replied" if is_reply else "scanned"
    company = (
        body.company_name
        or md.get("company_name")
        or (nd.split(".")[0].replace("-", " ").title() if nd else "Prospect")
    )[:200]
    industry = body.industry or md.get("industry")

    hs = body.hawk_score if body.hawk_score is not None else md.get("hawk_score")
    try:
        hawk_score = int(hs) if hs is not None else 0
    except (TypeError, ValueError):
        hawk_score = 0

    first = body.first_name or md.get("first_name")
    contact_name = str(first).strip() if first else None

    pr = _create_prospect_charlotte(
        nd=nd,
        stage=stage,
        assigned_rep_id=rep_id,
        company=company,
        industry=str(industry) if industry else None,
        contact_email=contact_email,
        contact_name=contact_name,
        hawk_score=hawk_score,
    )
    return str(pr["id"]), True


def _notify_charlotte_reply(*, prospect_id: str, body: EmailEventIn, sentiment: str | None) -> None:
    """WhatsApp rep + CEO; timeline activity (reply events)."""
    prospect = _get_prospect_row(prospect_id)
    if not prospect:
        return

    md = body.metadata or {}
    first = body.first_name or md.get("first_name") or prospect.get("contact_name")
    company = prospect.get("company_name") or prospect.get("domain") or "Prospect"
    score = prospect.get("hawk_score", 0) or 0
    base = CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com"

    rep_id = prospect.get("assigned_rep_id")
    rep_name = "Rep"
    rep_wa: str | None = None
    if rep_id:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_sb_headers(),
            params={"id": f"eq.{rep_id}", "select": "full_name,whatsapp_number", "limit": "1"},
            timeout=15.0,
        )
        if pr.status_code == 200 and pr.json():
            row = pr.json()[0]
            rep_name = str(row.get("full_name") or "Rep")
            w = row.get("whatsapp_number")
            rep_wa = str(w).strip() if w else None

    if rep_wa:
        try:
            msg = format_charlotte_reply_rep_message(
                company=str(company),
                first_name=str(first) if first else None,
                crm_base_url=base,
            )
            send_sms(rep_wa, msg)
        except Exception:
            logger.exception("SMS Charlotte rep alert failed prospect=%s", prospect_id)

    if CRM_CEO_PHONE_E164:
        try:
            ceo_msg = format_charlotte_reply_ceo_message(
                company=str(company),
                score=score,
                rep_name=rep_name,
            )
            send_sms(CRM_CEO_PHONE_E164, ceo_msg)
        except Exception:
            logger.exception("SMS Charlotte CEO alert failed")

    if VA_PHONE_NUMBER:
        try:
            send_sms(
                VA_PHONE_NUMBER,
                "New reply — "
                f"{company} — "
                f"{first or 'Prospect'} — "
                "Login to handle: securedbyhawk.com/crm/ai/replies",
            )
        except Exception:
            logger.exception("SMS VA alert failed")

    try:
        patch_data: dict[str, Any] = {"reply_received_at": datetime.now(timezone.utc).isoformat()}
        if sentiment == "positive":
            patch_data["is_hot"] = True
            patch_data["stage"] = "replied"
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={"id": f"eq.{prospect_id}"},
            json=patch_data,
            timeout=15.0,
        ).raise_for_status()
    except Exception:
        logger.exception("prospect reply_received_at patch failed")

    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/activities",
            headers=_sb_headers(),
            json={
                "prospect_id": prospect_id,
                "type": "charlotte_reply",
                "notes": "Charlotte reply received",
                "metadata": {
                    "source": body.source,
                    "external_id": body.external_id,
                    "subject": body.subject,
                },
            },
            timeout=15.0,
        ).raise_for_status()
    except Exception:
        logger.exception("Activity insert failed prospect=%s", prospect_id)


@router.post("/email-events")
def ingest_email_event(
    body: EmailEventIn,
    x_crm_webhook_secret: str | None = Header(default=None, alias="X-CRM-Webhook-Secret"),
):
    """
    Record an email engagement row for a prospect (outbound tool → HAWK API → Supabase).

    **Auth:** header `X-CRM-Webhook-Secret` must match `CRM_EMAIL_WEBHOOK_SECRET`.

    **Match prospect:** `prospect_id`, or `domain`, or derive domain from `contact_email`.

    **Charlotte / Smartlead reply:** if no prospect exists, creates one (round-robin closer),
    then WhatsApp rep + CEO and logs timeline activity.
    """
    _require_webhook_secret(x_crm_webhook_secret)

    pid, _created = _resolve_prospect_or_create(body)
    headers = _sb_headers()

    if body.external_id and body.external_id.strip():
        ext = body.external_id.strip()
        chk = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospect_email_events",
            headers=headers,
            params={
                "prospect_id": f"eq.{pid}",
                "external_id": f"eq.{ext}",
                "select": "id,created_at",
                "limit": "1",
            },
            timeout=20.0,
        )
        chk.raise_for_status()
        existing = chk.json()
        if existing:
            return {"ok": True, "duplicate": True, "id": existing[0]["id"], "prospect_id": pid}

    row = {
        "prospect_id": pid,
        "subject": body.subject,
        "sent_at": body.sent_at.isoformat() if body.sent_at else None,
        "opened_at": body.opened_at.isoformat() if body.opened_at else None,
        "clicked_at": body.clicked_at.isoformat() if body.clicked_at else None,
        "replied_at": body.replied_at.isoformat() if body.replied_at else None,
        "sequence_step": body.sequence_step,
        "source": (body.source or "webhook")[:64],
        "external_id": body.external_id.strip() if body.external_id else None,
        "metadata": body.metadata or {},
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/prospect_email_events",
        headers=headers,
        json=row,
        timeout=20.0,
    )
    if r.status_code == 409:
        logger.info("email event conflict prospect=%s external_id=%s", pid, body.external_id)
        raise HTTPException(status_code=409, detail="Conflict — duplicate external_id")
    r.raise_for_status()
    out = r.json()
    inserted = out[0] if isinstance(out, list) and out else out
    eid = inserted.get("id") if isinstance(inserted, dict) else None

    if body.replied_at is not None:
        md_sent = body.metadata or {}
        raw_sent = (body.sentiment or (md_sent.get("sentiment") if isinstance(md_sent.get("sentiment"), str) else "") or "").strip().lower()
        reply_sentiment = raw_sent or None
        _notify_charlotte_reply(prospect_id=pid, body=body, sentiment=reply_sentiment)

    return {"ok": True, "id": eid, "prospect_id": pid}


@router.get("/email-events/health")
def webhook_health():
    """Whether the email webhook is configured (no secrets returned)."""
    return {
        "configured": bool(WEBHOOK_SECRET and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        "has_secret": bool(WEBHOOK_SECRET),
        "has_supabase": bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
    }


# ── Smartlead Webhook (reply, bounce, spam complaint) ───────────────────


def _require_smartlead_webhook_secret(x_secret: str | None) -> None:
    if not SMARTLEAD_WEBHOOK_SECRET:
        logger.warning("CRM_SMARTLEAD_WEBHOOK_SECRET not set — rejecting Smartlead webhook")
        raise HTTPException(status_code=503, detail="Smartlead webhook not configured")
    if not x_secret or not secrets.compare_digest(x_secret, SMARTLEAD_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Smartlead webhook secret")


@router.post("/smartlead")
def smartlead_webhook(
    body: dict[str, Any] = Body(default_factory=dict),
    secret: str | None = Query(default=None),
):
    """
    Smartlead inbound webhook — handles reply, bounce, and spam complaint events.

    Configure in Smartlead dashboard (Settings > Webhooks):
    URL: POST https://intelligent-rejoicing-production.up.railway.app/api/crm/webhooks/smartlead?secret=<CRM_SMARTLEAD_WEBHOOK_SECRET>
    Events: reply received, email bounced, spam complaint.

    Auth via query parameter because Smartlead webhooks do not support custom headers.

    Replies are classified by ARIA (sentiment, confidence, reasoning),
    a response draft is generated, and the result is stored in aria_inbound_replies
    for human review/approval.

    Bounces and spam complaints update suppressions + aria_domain_health.
    """
    _require_smartlead_webhook_secret(secret)

    event_type = (
        body.get("event_type")
        or body.get("event")
        or body.get("type")
        or ""
    ).lower()

    import threading
    from services.aria_reply_handler import (
        process_bounce_event,
        process_reply_event,
        process_spam_complaint_event,
    )

    if event_type in ("reply", "email_reply", "reply_received"):
        # Process reply in background to avoid blocking webhook response
        threading.Thread(
            target=process_reply_event,
            args=(body,),
            daemon=True,
        ).start()
        return {"ok": True, "event": "reply", "status": "processing"}

    elif event_type in ("bounce", "email_bounce", "email_bounced"):
        result = process_bounce_event(body)
        return result

    elif event_type in ("spam", "spam_complaint", "complaint"):
        result = process_spam_complaint_event(body)
        return result

    else:
        logger.info("Smartlead webhook: unknown event_type=%r", event_type)
        return {"ok": True, "event": "unknown", "event_type": event_type}


# ── Cal.com webhook ─────────────────────────────────────────────────────


def _verify_cal_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not CAL_WEBHOOK_SECRET or not signature_header:
        return False
    sig = signature_header.strip()
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[-1].strip()
    mac = hmac.new(CAL_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    # Cal.com: createHmac("sha256", secret).update(body).digest("hex") — see cal.com sendPayload.ts
    expected_b64 = base64.b64encode(mac).decode("ascii")
    expected_hex = mac.hex()
    return secrets.compare_digest(sig, expected_b64) or secrets.compare_digest(sig, expected_hex)


def _cal_booking_payload(body: dict[str, Any]) -> dict[str, Any]:
    p = body.get("payload")
    if isinstance(p, dict):
        return p
    return body


def _cal_primary_attendee(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    attendees = payload.get("attendees") or []
    if not attendees or not isinstance(attendees[0], dict):
        return None, None
    a0 = attendees[0]
    email = (a0.get("email") or "").strip().lower() or None
    name = (a0.get("name") or "").strip() or None
    return email, name


def _cal_start_time_iso(payload: dict[str, Any]) -> str | None:
    for key in ("startTime", "start", "start_time"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _log_prospect_activity(*, prospect_id: str, type_: str, notes: str, metadata: dict[str, Any] | None = None) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/activities",
            headers=_sb_headers(),
            json={
                "prospect_id": prospect_id,
                "type": type_,
                "notes": notes[:2000],
                "metadata": metadata or {},
            },
            timeout=15.0,
        ).raise_for_status()
    except Exception:
        logger.exception("Cal webhook: activity log failed prospect=%s", prospect_id)


def _send_rep_sms_if_configured(*, rep_id: str | None, message: str) -> None:
    if not rep_id or not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    try:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_sb_headers(),
            params={"id": f"eq.{rep_id}", "select": "whatsapp_number", "limit": "1"},
            timeout=15.0,
        )
        pr.raise_for_status()
        rows = pr.json()
        if not rows:
            return
        wa = rows[0].get("whatsapp_number")
        if wa:
            send_sms(str(wa).strip(), message[:1600])
    except Exception:
        logger.exception("Cal webhook: rep SMS failed rep_id=%s", rep_id)


@router.post("/cal")
async def cal_com_webhook(
    request: Request,
    x_cal_signature_256: str | None = Header(default=None, alias="X-Cal-Signature-256"),
):
    """
    Cal.com → CRM: booking created / cancelled / rescheduled.
    Verifies HMAC-SHA256 (header `X-Cal-Signature-256`) with `CAL_WEBHOOK_SECRET`.
    """
    if not CAL_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Cal webhook not configured (CAL_WEBHOOK_SECRET)")
    raw = await request.body()
    if not _verify_cal_webhook_signature(raw, x_cal_signature_256):
        raise HTTPException(status_code=401, detail="Invalid Cal.com signature")
    try:
        body: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    trigger = str(
        body.get("triggerEvent") or body.get("type") or body.get("event") or ""
    ).upper()
    payload = _cal_booking_payload(body)
    attendee_email, attendee_name = _cal_primary_attendee(payload)
    start_iso = _cal_start_time_iso(payload)
    base = (CRM_PUBLIC_BASE_URL or "https://securedbyhawk.com").rstrip("/")

    if not attendee_email:
        return {"ok": True, "ignored": True, "reason": "no_attendee_email", "trigger": trigger}

    prospect = _fetch_prospect_by_contact_email(attendee_email)
    now_iso = datetime.now(timezone.utc).isoformat()

    if trigger == "BOOKING_CREATED":
        if not prospect:
            return {"ok": True, "matched": False, "trigger": trigger}
        pid = str(prospect["id"])
        company = prospect.get("company_name") or prospect.get("domain") or "Prospect"
        try:
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
                params={"id": f"eq.{pid}"},
                json={
                    "stage": "call_booked",
                    "is_hot": True,
                    "call_booked_at": now_iso,
                    "last_activity_at": now_iso,
                },
                timeout=20.0,
            ).raise_for_status()
        except Exception:
            logger.exception("Cal BOOKING_CREATED prospect patch failed prospect=%s", pid)
            raise HTTPException(status_code=502, detail="Prospect update failed") from None

        time_note = start_iso or "time TBD"
        _log_prospect_activity(
            prospect_id=pid,
            type_="call_booked",
            notes=f"Cal.com booking — {time_note} — {attendee_name or attendee_email}",
            metadata={"startTime": start_iso, "attendee_name": attendee_name, "attendee_email": attendee_email},
        )
        ceo_msg = (
            f"HAWK — Call booked: {company}\n"
            f"Contact: {attendee_name or '—'} ({attendee_email})\n"
            f"Time: {time_note}\n"
            f"CRM: {base}/crm/prospects/{pid}"
        )
        try:
            send_ceo_sms(ceo_msg[:1600])
        except Exception:
            logger.exception("Cal BOOKING_CREATED CEO SMS failed")
        rep_msg = (
            f"Call booked: {company} — {attendee_name or attendee_email} @ {time_note}. "
            f"CRM: {base}/crm/prospects/{pid}"
        )
        _send_rep_sms_if_configured(rep_id=prospect.get("assigned_rep_id"), message=rep_msg)
        return {"ok": True, "matched": True, "prospect_id": pid, "trigger": trigger}

    if trigger == "BOOKING_CANCELLED":
        if not prospect:
            return {"ok": True, "matched": False, "trigger": trigger}
        pid = str(prospect["id"])
        company = prospect.get("company_name") or prospect.get("domain") or "Prospect"
        try:
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
                params={"id": f"eq.{pid}"},
                json={"stage": "replied", "last_activity_at": now_iso},
                timeout=20.0,
            ).raise_for_status()
        except Exception:
            logger.exception("Cal BOOKING_CANCELLED prospect patch failed prospect=%s", pid)
            raise HTTPException(status_code=502, detail="Prospect update failed") from None
        _log_prospect_activity(
            prospect_id=pid,
            type_="call_cancelled",
            notes=f"Cal.com cancellation — was {start_iso or 'unknown time'}",
            metadata={"attendee_email": attendee_email},
        )
        try:
            send_ceo_sms(
                f"HAWK — Call cancelled: {company} ({attendee_email}). CRM: {base}/crm/prospects/{pid}"[:1600]
            )
        except Exception:
            logger.exception("Cal BOOKING_CANCELLED CEO SMS failed")
        return {"ok": True, "matched": True, "prospect_id": pid, "trigger": trigger}

    if trigger == "BOOKING_RESCHEDULED":
        if not prospect:
            return {"ok": True, "matched": False, "trigger": trigger}
        pid = str(prospect["id"])
        company = prospect.get("company_name") or prospect.get("domain") or "Prospect"
        time_note = start_iso or "new time TBD"
        _log_prospect_activity(
            prospect_id=pid,
            type_="call_rescheduled",
            notes=f"Cal.com rescheduled — {time_note}",
            metadata={"startTime": start_iso, "attendee_email": attendee_email},
        )
        try:
            send_ceo_sms(
                f"HAWK — Call rescheduled: {company} — new time: {time_note}. CRM: {base}/crm/prospects/{pid}"[:1600]
            )
        except Exception:
            logger.exception("Cal BOOKING_RESCHEDULED CEO SMS failed")
        return {"ok": True, "matched": True, "prospect_id": pid, "trigger": trigger}

    return {"ok": True, "trigger": trigger, "note": "no_handler"}
