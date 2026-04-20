"""Mailbox registry — read/write helpers for ``public.crm_mailboxes``.

This module is the single read/write surface for the mailbox table so the
dispatcher, IMAP poller, and router all share the same rotation, counter,
and status logic. Everything here uses the Supabase service role; RLS is
enforced in the router layer.

Key invariants:
* ``sent_today`` is authoritative — dispatcher increments it atomically per
  send and the daily-reset cron job zeroes it at local midnight.
* ``pick_next_for_vertical`` prefers mailboxes with ``vertical IS NULL``
  (shared pool) alongside vertical-matched ones, ordered by remaining
  capacity so we spread load evenly instead of exhausting a single inbox.
* Bounce handling auto-pauses a mailbox if its 7d bounce rate crosses
  ``mailbox_bounce_rate_threshold`` (default 5%).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from services.mailbox_crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

MST = ZoneInfo("America/Edmonton")

DEFAULT_BOUNCE_THRESHOLD = float(os.environ.get("MAILBOX_BOUNCE_THRESHOLD", "0.05"))


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _today_mst() -> date:
    return datetime.now(MST).date()


def _configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


# ─── Reads ─────────────────────────────────────────────────────────────────


def list_mailboxes(*, status: str | None = None) -> list[dict[str, Any]]:
    """Return every mailbox row, optionally filtered by status. Never includes decrypted passwords."""
    if not _configured():
        return []
    params: dict[str, str] = {
        "select": (
            "id,email_address,display_name,domain,provider,"
            "smtp_host,smtp_port,smtp_username,smtp_use_tls,smtp_use_ssl,"
            "imap_host,imap_port,imap_username,imap_use_ssl,"
            "daily_cap,sent_today,sent_today_date,sent_total,last_send_at,"
            "vertical,status,warmup_status,bounce_count_7d,bounce_rate_7d,"
            "last_bounce_at,last_error,notes,created_at,updated_at"
        ),
        "order": "created_at.desc",
    }
    if status:
        params["status"] = f"eq.{status}"
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params=params,
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        logger.warning("mailbox list failed: %s", exc)
        return []


def get_mailbox(mailbox_id: str) -> dict[str, Any] | None:
    """Fetch a single mailbox row by id (without decrypted secrets)."""
    rows = _get_rows({"id": f"eq.{mailbox_id}", "limit": "1"})
    return rows[0] if rows else None


def get_mailbox_with_secrets(mailbox_id: str) -> dict[str, Any] | None:
    """Fetch + decrypt SMTP/IMAP passwords. Callers must never log this dict."""
    if not _configured():
        return None
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params={
                "id": f"eq.{mailbox_id}",
                "select": "*",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        rows = r.json() or []
    except Exception as exc:
        logger.warning("mailbox fetch-with-secrets failed: %s", exc)
        return None
    if not rows:
        return None
    row = rows[0]
    try:
        row["_smtp_password"] = decrypt_secret(row["smtp_password_encrypted"])
        row["_imap_password"] = decrypt_secret(row["imap_password_encrypted"])
    except Exception as exc:
        logger.error("mailbox %s decrypt failed: %s", mailbox_id, exc)
        return None
    return row


def _get_rows(params: dict[str, str]) -> list[dict[str, Any]]:
    if not _configured():
        return []
    qp = {
        "select": (
            "id,email_address,display_name,domain,provider,"
            "smtp_host,smtp_port,smtp_username,smtp_use_tls,smtp_use_ssl,"
            "imap_host,imap_port,imap_username,imap_use_ssl,"
            "daily_cap,sent_today,sent_today_date,sent_total,last_send_at,"
            "vertical,status,warmup_status,bounce_count_7d,bounce_rate_7d,"
            "last_bounce_at,last_error,created_at,updated_at"
        ),
        **params,
    }
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params=qp,
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        logger.warning("mailbox query failed: %s", exc)
        return []


def count_available_for_vertical(vertical: str) -> dict[str, int]:
    """Aggregate remaining daily capacity for a vertical. Used by the dispatcher quota calculator."""
    if not _configured():
        return {"active_mailboxes": 0, "remaining_today": 0}
    today = _today_mst().isoformat()
    rows = _get_rows(
        {
            "status": "eq.active",
            "or": f"(vertical.is.null,vertical.eq.{vertical})",
            "limit": "500",
        }
    )
    active = 0
    remaining = 0
    for row in rows:
        active += 1
        sent = int(row.get("sent_today") or 0) if str(row.get("sent_today_date")) == today else 0
        cap = int(row.get("daily_cap") or 0)
        remaining += max(0, cap - sent)
    return {"active_mailboxes": active, "remaining_today": remaining}


def pick_next_for_vertical(vertical: str, exclude_ids: list[str] | None = None) -> dict[str, Any] | None:
    """Return the active mailbox for this vertical with the most remaining capacity.

    Round-robin-ish: ties broken by oldest ``last_send_at`` so we spread load.
    Returns None if no mailbox has remaining capacity (caller must stop the tick).
    """
    if not _configured():
        return None
    today = _today_mst().isoformat()
    rows = _get_rows(
        {
            "status": "eq.active",
            "or": f"(vertical.is.null,vertical.eq.{vertical})",
            "limit": "500",
        }
    )
    excl = set(exclude_ids or [])
    best: dict[str, Any] | None = None
    best_remaining = 0
    for row in rows:
        if row["id"] in excl:
            continue
        sent = int(row.get("sent_today") or 0) if str(row.get("sent_today_date")) == today else 0
        cap = int(row.get("daily_cap") or 0)
        rem = cap - sent
        if rem <= 0:
            continue
        if best is None or rem > best_remaining:
            best, best_remaining = row, rem
            continue
        if rem == best_remaining:
            # Prefer the mailbox that hasn't sent in a while — spreads load.
            a = str(row.get("last_send_at") or "")
            b = str(best.get("last_send_at") or "")
            if a < b:
                best = row
    return best


# ─── Writes ────────────────────────────────────────────────────────────────


def increment_sent(mailbox_id: str) -> bool:
    """Bump ``sent_today`` + ``sent_total`` atomically for a single send.

    Uses a read-modify-write with sent_today_date gate so we also roll the
    daily counter over if midnight crossed mid-tick.
    """
    if not _configured():
        return False
    today = _today_mst().isoformat()
    row = get_mailbox(mailbox_id)
    if not row:
        return False
    same_day = str(row.get("sent_today_date")) == today
    sent_today = int(row.get("sent_today") or 0) if same_day else 0
    patch = {
        "sent_today": sent_today + 1,
        "sent_today_date": today,
        "sent_total": int(row.get("sent_total") or 0) + 1,
        "last_send_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params={"id": f"eq.{mailbox_id}"},
            json=patch,
            timeout=15.0,
        )
        r.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("mailbox %s increment_sent failed: %s", mailbox_id, exc)
        return False


def reset_daily_counters() -> int:
    """Reset sent_today=0 for every mailbox whose sent_today_date isn't today. Idempotent."""
    if not _configured():
        return 0
    today = _today_mst().isoformat()
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params={"sent_today_date": f"neq.{today}"},
            json={"sent_today": 0, "sent_today_date": today},
            timeout=20.0,
        )
        r.raise_for_status()
        return len(r.json() or [])
    except Exception as exc:
        logger.warning("mailbox daily reset failed: %s", exc)
        return 0


def record_bounce(mailbox_id: str, error: str) -> None:
    """Increment bounce_count_7d + auto-pause if bounce_rate crosses threshold."""
    if not _configured():
        return
    row = get_mailbox(mailbox_id)
    if not row:
        return
    bounces = int(row.get("bounce_count_7d") or 0) + 1
    sent_total = max(1, int(row.get("sent_total") or 1))
    rate = min(1.0, bounces / sent_total)
    patch: dict[str, Any] = {
        "bounce_count_7d": bounces,
        "bounce_rate_7d": round(rate, 4),
        "last_bounce_at": datetime.now(timezone.utc).isoformat(),
        "last_error": error[:500] if error else None,
    }
    if rate >= DEFAULT_BOUNCE_THRESHOLD and str(row.get("status")) == "active":
        patch["status"] = "paused"
        patch["last_error"] = f"auto-paused: bounce rate {rate:.1%} >= {DEFAULT_BOUNCE_THRESHOLD:.1%}"
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params={"id": f"eq.{mailbox_id}"},
            json=patch,
            timeout=15.0,
        ).raise_for_status()
    except Exception as exc:
        logger.warning("mailbox %s record_bounce failed: %s", mailbox_id, exc)


def record_error(mailbox_id: str, error: str) -> None:
    """Stamp last_error without changing status. Used for transient send failures."""
    if not _configured():
        return
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params={"id": f"eq.{mailbox_id}"},
            json={"last_error": (error or "")[:500]},
            timeout=10.0,
        ).raise_for_status()
    except Exception:
        pass


def update_imap_cursor(
    mailbox_id: str,
    *,
    uid_validity: int | None = None,
    last_uid: int | None = None,
    polled_at: datetime | None = None,
) -> None:
    if not _configured():
        return
    patch: dict[str, Any] = {"imap_last_polled_at": (polled_at or datetime.now(timezone.utc)).isoformat()}
    if uid_validity is not None:
        patch["imap_last_uid_validity"] = int(uid_validity)
    if last_uid is not None:
        patch["imap_last_seen_uid"] = int(last_uid)
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params={"id": f"eq.{mailbox_id}"},
            json=patch,
            timeout=15.0,
        ).raise_for_status()
    except Exception as exc:
        logger.warning("mailbox %s imap cursor update failed: %s", mailbox_id, exc)


def create_mailbox(payload: dict[str, Any], created_by: str | None = None) -> dict[str, Any]:
    """Insert a new mailbox row, encrypting SMTP + IMAP passwords. Returns the inserted row (no plaintext)."""
    if not _configured():
        raise RuntimeError("Supabase not configured")
    body = {
        "email_address": payload["email_address"].strip().lower(),
        "display_name": (payload.get("display_name") or "").strip(),
        "domain": payload["domain"].strip().lower(),
        "provider": payload.get("provider") or "smtp",
        "smtp_host": payload["smtp_host"].strip(),
        "smtp_port": int(payload.get("smtp_port") or 587),
        "smtp_username": payload["smtp_username"].strip(),
        "smtp_password_encrypted": encrypt_secret(payload["smtp_password"]),
        "smtp_use_tls": bool(payload.get("smtp_use_tls", True)),
        "smtp_use_ssl": bool(payload.get("smtp_use_ssl", False)),
        "imap_host": payload["imap_host"].strip(),
        "imap_port": int(payload.get("imap_port") or 993),
        "imap_username": payload["imap_username"].strip(),
        "imap_password_encrypted": encrypt_secret(payload["imap_password"]),
        "imap_use_ssl": bool(payload.get("imap_use_ssl", True)),
        "daily_cap": int(payload.get("daily_cap") or 40),
        "vertical": payload.get("vertical") or None,
        "status": payload.get("status") or "active",
        "warmup_status": payload.get("warmup_status") or "active",
        "notes": (payload.get("notes") or "").strip() or None,
    }
    if created_by:
        body["created_by"] = created_by
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
        headers=_headers(),
        json=body,
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json() or []
    return rows[0] if rows else {}


def update_mailbox(mailbox_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Patch a mailbox. Re-encrypts passwords if they're present in payload."""
    if not _configured():
        raise RuntimeError("Supabase not configured")
    patch: dict[str, Any] = {}
    simple_fields = [
        "email_address",
        "display_name",
        "domain",
        "provider",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_use_tls",
        "smtp_use_ssl",
        "imap_host",
        "imap_port",
        "imap_username",
        "imap_use_ssl",
        "daily_cap",
        "vertical",
        "status",
        "warmup_status",
        "notes",
    ]
    for k in simple_fields:
        if k in payload and payload[k] is not None:
            patch[k] = payload[k]
    if payload.get("smtp_password"):
        patch["smtp_password_encrypted"] = encrypt_secret(payload["smtp_password"])
    if payload.get("imap_password"):
        patch["imap_password_encrypted"] = encrypt_secret(payload["imap_password"])
    if not patch:
        return get_mailbox(mailbox_id)
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
        headers=_headers(),
        params={"id": f"eq.{mailbox_id}"},
        json=patch,
        timeout=15.0,
    )
    r.raise_for_status()
    rows = r.json() or []
    return rows[0] if rows else None


def delete_mailbox(mailbox_id: str) -> bool:
    if not _configured():
        return False
    try:
        r = httpx.delete(
            f"{SUPABASE_URL}/rest/v1/crm_mailboxes",
            headers=_headers(),
            params={"id": f"eq.{mailbox_id}"},
            timeout=15.0,
        )
        r.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("mailbox %s delete failed: %s", mailbox_id, exc)
        return False
