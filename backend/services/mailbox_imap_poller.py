"""IMAP reply poller — replaces the Smartlead webhook for reply detection.

For each active mailbox, connects to its IMAP server, fetches UNSEEN messages
from INBOX, and threads any replies back to the originating prospect via the
``In-Reply-To`` / ``References`` headers we set at send time (message_id is
stored on ``prospects.sent_message_id``).

When a reply is detected:
* The prospect advances to ``stage=replied`` + ``pipeline_status=contacted``
  (reuse existing states — we don't create new ones).
* A ``prospect_email_events`` row is inserted for audit.
* ``last_activity_at`` is stamped so aging heuristics stay accurate.
* ARIA's command-center summarizer can pick it up on next tick (no direct
  webhook fire in v1 — keeps this module side-effect light).

The poller is intentionally defensive: a broken mailbox can't stop replies
from being found on a healthy mailbox. Each mailbox is polled independently
with its own error log line.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

import httpx

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from services import mailbox_registry

logger = logging.getLogger(__name__)

# IMAP fetches use a 60s per-mailbox ceiling so a hung inbox can't block the tick.
_IMAP_TIMEOUT = 60.0

_MSG_ID_RE = re.compile(r"<[^>]+>")


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _find_prospect_by_message_id(message_ids: list[str]) -> dict[str, Any] | None:
    """Match any of the given outbound Message-IDs to a prospect row."""
    if not _configured() or not message_ids:
        return None
    # PostgREST `in.()` with quoted strings; messages ids contain <> so we strip.
    clean = [m.strip("<> ").strip() for m in message_ids if m]
    if not clean:
        return None
    quoted = ",".join(f'"{m}"' for m in clean)
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_headers(),
            params={
                "select": "id,domain,company_name,contact_email,stage,pipeline_status,sent_message_id,industry",
                "sent_message_id": f"in.({quoted})",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("reply-poll prospect lookup failed: %s", exc)
        return None


def _find_prospect_by_reply_address(reply_from: str) -> dict[str, Any] | None:
    """Fallback: when threading headers are missing, match by the replier's email."""
    if not _configured() or not reply_from:
        return None
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_headers(),
            params={
                "select": "id,domain,company_name,contact_email,stage,pipeline_status,sent_message_id,industry",
                "contact_email": f"eq.{reply_from.lower()}",
                "sent_message_id": "not.is.null",
                "order": "dispatched_at.desc.nullslast",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("reply-poll fallback lookup failed: %s", exc)
        return None


def _mark_prospect_replied(
    prospect_id: str,
    *,
    reply_from: str,
    reply_subject: str,
    reply_body_snippet: str,
    mailbox_id: str,
) -> None:
    """Flip prospect → replied + log an email event. DB-guarded on stage to avoid regression."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_headers(),
            params={
                "id": f"eq.{prospect_id}",
                "stage": "in.(sent_email,new,scanning,scanned)",
            },
            json={
                "stage": "replied",
                "pipeline_status": "contacted",
                "last_activity_at": now_iso,
            },
            timeout=15.0,
        ).raise_for_status()
    except Exception as exc:
        logger.warning("reply-poll prospect %s mark-replied failed: %s", prospect_id, exc)

    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/prospect_email_events",
            headers=_headers(),
            json={
                "prospect_id": prospect_id,
                "subject": (reply_subject or "")[:500] or None,
                "replied_at": now_iso,
                "source": "imap_poller",
                "metadata": {
                    "reply_from": (reply_from or "").lower()[:255] or None,
                    "body_snippet": (reply_body_snippet or "")[:2000] or None,
                    "mailbox_id": mailbox_id,
                },
            },
            timeout=15.0,
        ).raise_for_status()
    except Exception as exc:
        # Audit-log-only failure — not fatal.
        logger.info("reply-poll email_event insert skipped (%s): %s", prospect_id, exc)


def _extract_body_snippet(msg: email.message.Message) -> str:
    """Best-effort plain-text body extractor (text/plain preferred, strips HTML tags otherwise)."""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        return re.sub(r"<[^>]+>", " ", html)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    except Exception:
        pass
    return ""


def _poll_single_mailbox(mailbox_id: str) -> dict[str, Any]:
    row = mailbox_registry.get_mailbox_with_secrets(mailbox_id)
    if not row:
        return {"ok": False, "error": "not found", "processed": 0, "replies": 0}
    if str(row.get("status")) != "active":
        return {"ok": True, "skipped": True, "reason": f"status={row.get('status')}", "processed": 0, "replies": 0}

    host = str(row["imap_host"])
    port = int(row["imap_port"])
    user = str(row["imap_username"])
    password = str(row["_imap_password"])
    use_ssl = bool(row.get("imap_use_ssl", True))

    processed = 0
    replies = 0
    last_uid_seen: int | None = None
    try:
        client: imaplib.IMAP4 = (
            imaplib.IMAP4_SSL(host, port, timeout=_IMAP_TIMEOUT)
            if use_ssl
            else imaplib.IMAP4(host, port, timeout=_IMAP_TIMEOUT)
        )
    except Exception as exc:
        err = f"IMAP connect failed: {exc.__class__.__name__}: {exc}"
        logger.warning("mailbox %s %s", mailbox_id, err)
        mailbox_registry.record_error(mailbox_id, err)
        return {"ok": False, "error": err, "processed": 0, "replies": 0}

    try:
        client.login(user, password)
        client.select("INBOX", readonly=False)
        typ, data = client.uid("search", None, "UNSEEN")
        if typ != "OK":
            return {"ok": False, "error": f"SEARCH {typ}", "processed": 0, "replies": 0}
        uids = (data[0] or b"").split()
        for uid in uids:
            uid_str = uid.decode("ascii") if isinstance(uid, bytes) else str(uid)
            typ, fetched = client.uid("fetch", uid, "(RFC822)")
            processed += 1
            try:
                last_uid_seen = int(uid_str)
            except ValueError:
                last_uid_seen = None
            if typ != "OK" or not fetched:
                continue
            raw = fetched[0][1] if isinstance(fetched[0], tuple) else None
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            in_reply_to = msg.get("In-Reply-To", "") or ""
            references = msg.get("References", "") or ""
            candidate_ids = _MSG_ID_RE.findall(" ".join([in_reply_to, references]))
            prospect = _find_prospect_by_message_id(candidate_ids)
            if not prospect:
                reply_from = parseaddr(msg.get("From", ""))[1]
                prospect = _find_prospect_by_reply_address(reply_from)
            if not prospect:
                continue
            reply_from = parseaddr(msg.get("From", ""))[1]
            reply_subject = msg.get("Subject", "") or ""
            body_snippet = _extract_body_snippet(msg)[:2000]
            _mark_prospect_replied(
                str(prospect["id"]),
                reply_from=reply_from,
                reply_subject=reply_subject,
                reply_body_snippet=body_snippet,
                mailbox_id=mailbox_id,
            )
            replies += 1
    except Exception as exc:
        err = f"IMAP poll error: {exc.__class__.__name__}: {exc}"
        logger.warning("mailbox %s %s", mailbox_id, err)
        mailbox_registry.record_error(mailbox_id, err)
        return {"ok": False, "error": err, "processed": processed, "replies": replies}
    finally:
        try:
            client.logout()
        except Exception:
            pass

    mailbox_registry.update_imap_cursor(
        mailbox_id,
        last_uid=last_uid_seen,
        polled_at=datetime.now(timezone.utc),
    )
    return {"ok": True, "processed": processed, "replies": replies}


def run_imap_reply_poll(mailbox_ids: list[str] | None = None) -> dict[str, Any]:
    """Poll every active mailbox (or the provided subset). Returns a per-mailbox breakdown."""
    if not _configured():
        return {"ok": False, "reason": "supabase not configured"}
    rows = mailbox_registry.list_mailboxes(status="active")
    target_ids = set(mailbox_ids or [r["id"] for r in rows])
    results: dict[str, Any] = {"ok": True, "mailboxes": {}, "totals": {"processed": 0, "replies": 0}}
    for row in rows:
        mid = str(row["id"])
        if mid not in target_ids:
            continue
        outcome = _poll_single_mailbox(mid)
        results["mailboxes"][row["email_address"]] = outcome
        results["totals"]["processed"] += int(outcome.get("processed") or 0)
        results["totals"]["replies"] += int(outcome.get("replies") or 0)
    return results


def test_imap_login(mailbox_id: str) -> dict[str, Any]:
    """Probe IMAP connectivity + login without touching messages. For the UI Test button."""
    row = mailbox_registry.get_mailbox_with_secrets(mailbox_id)
    if not row:
        return {"ok": False, "error": "mailbox not found"}
    host = str(row["imap_host"])
    port = int(row["imap_port"])
    use_ssl = bool(row.get("imap_use_ssl", True))
    try:
        client: imaplib.IMAP4 = (
            imaplib.IMAP4_SSL(host, port, timeout=15.0)
            if use_ssl
            else imaplib.IMAP4(host, port, timeout=15.0)
        )
        client.login(str(row["imap_username"]), str(row["_imap_password"]))
        client.select("INBOX", readonly=True)
        client.logout()
        return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
