"""Direct SMTP sender for HAWK's native cold-outbound dispatcher.

Replaces the Smartlead bulk-upload path. Given a mailbox row (with decrypted
SMTP creds) and a prospect, we construct an RFC 5322 email (plaintext +
optional HTML alt), assign a ``Message-ID`` we control so the IMAP reply
poller can thread replies back to the originating prospect, and deliver via
``aiosmtplib``.

Error handling:
* 4xx SMTP errors → treated as transient; caller can retry the prospect next
  tick. We do NOT mark the mailbox paused.
* 5xx SMTP errors / auth failures → mailbox error stamped; dispatcher skips
  it for the rest of the tick.
* Hard bounces detected at send-time (domain-not-found, recipient-rejected)
  are recorded via ``mailbox_registry.record_bounce`` so the bounce-rate
  auto-pause logic kicks in when we have a real problem mailbox.

Deliverability:
* We set a proper ``Message-ID`` using the sending mailbox's domain so DKIM
  alignment stays intact.
* ``Return-Path`` / envelope-from matches the mailbox's authenticated user,
  required for SPF alignment on Google Workspace / Microsoft 365.
* ``List-Unsubscribe`` (mailto + one-click) is optional but strongly
  recommended — emitted when ``unsubscribe_mailto`` is provided.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import re
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import aiosmtplib

from services import mailbox_registry

logger = logging.getLogger(__name__)


# Common SMTP bounce signatures we care about for the auto-pause heuristic.
_HARD_BOUNCE_PATTERNS = (
    re.compile(r"5\.1\.[12]"),  # bad destination / unknown recipient
    re.compile(r"no such user", re.I),
    re.compile(r"user unknown", re.I),
    re.compile(r"domain.*not.*found", re.I),
    re.compile(r"relay.*denied", re.I),
)

_AUTH_FAILURE_PATTERNS = (
    re.compile(r"authentication (failed|unsuccessful|invalid)", re.I),
    re.compile(r"5\.7\.(0|8)"),
)


@dataclass
class SendResult:
    ok: bool
    mailbox_id: str
    message_id: str | None
    error: str | None = None
    was_bounce: bool = False
    was_auth_failure: bool = False


def build_message(
    *,
    from_email: str,
    from_name: str,
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    reply_to: str | None = None,
    unsubscribe_mailto: str | None = None,
) -> tuple[EmailMessage, str]:
    """Construct an RFC 5322 message + return (message, message_id_we_generated)."""
    domain = from_email.split("@", 1)[1] if "@" in from_email else "localhost"
    message_id = email.utils.make_msgid(idstring=uuid.uuid4().hex[:16], domain=domain)

    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((from_name or "", from_email))
    msg["To"] = email.utils.formataddr((to_name or "", to_email))
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = message_id
    if reply_to:
        msg["Reply-To"] = reply_to
    if unsubscribe_mailto:
        msg["List-Unsubscribe"] = f"<mailto:{unsubscribe_mailto}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    return msg, message_id


async def send_via_mailbox_async(
    mailbox_id: str,
    *,
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    reply_to: str | None = None,
    unsubscribe_mailto: str | None = None,
) -> SendResult:
    """Connect to the mailbox's SMTP server, authenticate, send one message."""
    row = mailbox_registry.get_mailbox_with_secrets(mailbox_id)
    if not row:
        return SendResult(ok=False, mailbox_id=mailbox_id, message_id=None, error="mailbox not found")
    if str(row.get("status")) != "active":
        return SendResult(
            ok=False,
            mailbox_id=mailbox_id,
            message_id=None,
            error=f"mailbox status={row.get('status')}",
        )

    from_email = str(row["email_address"])
    from_name = str(row.get("display_name") or "")
    smtp_host = str(row["smtp_host"])
    smtp_port = int(row["smtp_port"])
    smtp_user = str(row["smtp_username"])
    smtp_pass = str(row["_smtp_password"])
    use_tls = bool(row.get("smtp_use_tls"))
    use_ssl = bool(row.get("smtp_use_ssl"))

    msg, message_id = build_message(
        from_email=from_email,
        from_name=from_name,
        to_email=to_email,
        to_name=to_name,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        reply_to=reply_to or from_email,
        unsubscribe_mailto=unsubscribe_mailto,
    )

    tls_context = ssl.create_default_context() if (use_tls or use_ssl) else None
    try:
        async with aiosmtplib.SMTP(
            hostname=smtp_host,
            port=smtp_port,
            use_tls=use_ssl,
            start_tls=use_tls and not use_ssl,
            tls_context=tls_context,
            timeout=30.0,
        ) as client:
            await client.login(smtp_user, smtp_pass)
            await client.send_message(msg)
    except aiosmtplib.SMTPAuthenticationError as exc:
        err = f"SMTP auth failed: {exc}"
        logger.warning("mailbox %s %s", mailbox_id, err)
        mailbox_registry.record_error(mailbox_id, err)
        return SendResult(
            ok=False,
            mailbox_id=mailbox_id,
            message_id=None,
            error=err,
            was_auth_failure=True,
        )
    except aiosmtplib.SMTPRecipientsRefused as exc:
        err = f"SMTP recipients refused: {exc}"
        logger.info("mailbox %s %s (prospect bounce)", mailbox_id, err)
        # Recipient-side bounce — do NOT auto-pause the mailbox; this is a prospect problem.
        return SendResult(
            ok=False,
            mailbox_id=mailbox_id,
            message_id=None,
            error=err,
            was_bounce=True,
        )
    except aiosmtplib.SMTPResponseException as exc:
        err = f"SMTP {exc.code}: {exc.message}"
        logger.warning("mailbox %s %s", mailbox_id, err)
        if _looks_like_hard_bounce(err):
            mailbox_registry.record_bounce(mailbox_id, err)
            return SendResult(
                ok=False,
                mailbox_id=mailbox_id,
                message_id=None,
                error=err,
                was_bounce=True,
            )
        mailbox_registry.record_error(mailbox_id, err)
        return SendResult(ok=False, mailbox_id=mailbox_id, message_id=None, error=err)
    except Exception as exc:
        err = f"SMTP unexpected error: {exc.__class__.__name__}: {exc}"
        logger.warning("mailbox %s %s", mailbox_id, err)
        mailbox_registry.record_error(mailbox_id, err)
        return SendResult(ok=False, mailbox_id=mailbox_id, message_id=None, error=err)

    # Success — bump the per-mailbox counter.
    mailbox_registry.increment_sent(mailbox_id)
    return SendResult(ok=True, mailbox_id=mailbox_id, message_id=message_id, error=None)


def send_via_mailbox(
    mailbox_id: str,
    *,
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    reply_to: str | None = None,
    unsubscribe_mailto: str | None = None,
) -> SendResult:
    """Sync wrapper — safe to call from httpx-based code paths that aren't async."""
    return asyncio.run(
        send_via_mailbox_async(
            mailbox_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            reply_to=reply_to,
            unsubscribe_mailto=unsubscribe_mailto,
        )
    )


def test_smtp_login(mailbox_id: str) -> dict[str, Any]:
    """Probe SMTP connectivity + auth without sending anything. For the Test button in the UI."""
    async def _run() -> dict[str, Any]:
        row = mailbox_registry.get_mailbox_with_secrets(mailbox_id)
        if not row:
            return {"ok": False, "error": "mailbox not found"}
        use_tls = bool(row.get("smtp_use_tls"))
        use_ssl = bool(row.get("smtp_use_ssl"))
        tls_context = ssl.create_default_context() if (use_tls or use_ssl) else None
        try:
            async with aiosmtplib.SMTP(
                hostname=str(row["smtp_host"]),
                port=int(row["smtp_port"]),
                use_tls=use_ssl,
                start_tls=use_tls and not use_ssl,
                tls_context=tls_context,
                timeout=15.0,
            ) as client:
                await client.login(str(row["smtp_username"]), str(row["_smtp_password"]))
            return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}
        except Exception as exc:
            return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}

    return asyncio.run(_run())


def _looks_like_hard_bounce(text: str) -> bool:
    for pat in _HARD_BOUNCE_PATTERNS:
        if pat.search(text):
            return True
    return False


def _looks_like_auth_failure(text: str) -> bool:
    for pat in _AUTH_FAILURE_PATTERNS:
        if pat.search(text):
            return True
    return False
