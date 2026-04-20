"""CRM mailbox management — CEO/HOS only.

Exposes the CRUD API used by ``/crm/settings/mailboxes`` plus helpers for
testing SMTP/IMAP connectivity and running one-off reply polls. All write
endpoints require a privileged role (same gate as ``crm_settings``).
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from routers.crm_settings import require_ceo
from services import mailbox_imap_poller, mailbox_registry
from services.mailbox_crypto import MailboxCryptoError, is_configured as crypto_configured
from services.mailbox_smtp_sender import test_smtp_login

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/settings/mailboxes", tags=["crm-mailboxes"])


class MailboxCreate(BaseModel):
    email_address: EmailStr
    display_name: str = ""
    domain: str = Field(..., min_length=2)
    provider: str = "smtp"
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str = Field(..., min_length=1)
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str = Field(..., min_length=1)
    imap_use_ssl: bool = True
    daily_cap: int = 40
    vertical: str | None = None
    status: str = "active"
    warmup_status: str = "active"
    notes: str | None = None


class MailboxUpdate(BaseModel):
    email_address: EmailStr | None = None
    display_name: str | None = None
    domain: str | None = None
    provider: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None  # only set when user provides a new one
    smtp_use_tls: bool | None = None
    smtp_use_ssl: bool | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = None
    imap_use_ssl: bool | None = None
    daily_cap: int | None = None
    vertical: str | None = None
    status: str | None = None
    warmup_status: str | None = None
    notes: str | None = None


class BulkImportPayload(BaseModel):
    csv_text: str | None = None
    rows: list[MailboxCreate] | None = None


def _ensure_crypto() -> None:
    if not crypto_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "MAILBOX_ENCRYPTION_KEY is not set on the backend. "
                "Generate one with `python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
                "and set it in the Railway environment before creating mailboxes."
            ),
        )


@router.get("")
def list_all(_: str = Depends(require_ceo)) -> dict[str, Any]:
    """Return every mailbox row (secrets redacted)."""
    rows = mailbox_registry.list_mailboxes()
    active = [r for r in rows if str(r.get("status")) == "active"]
    capacity = 0
    used = 0
    for r in active:
        cap = int(r.get("daily_cap") or 0)
        capacity += cap
        # Only count sent_today if it's today's row; mailbox_registry takes care of reset.
        used += int(r.get("sent_today") or 0)
    return {
        "mailboxes": rows,
        "health": {
            "total": len(rows),
            "active": len(active),
            "paused": len([r for r in rows if str(r.get("status")) == "paused"]),
            "capacity_today": capacity,
            "used_today": used,
            "remaining_today": max(0, capacity - used),
            "crypto_configured": crypto_configured(),
        },
    }


@router.post("")
def create(payload: MailboxCreate, uid: str = Depends(require_ceo)) -> dict[str, Any]:
    _ensure_crypto()
    try:
        row = mailbox_registry.create_mailbox(payload.model_dump(), created_by=uid)
    except MailboxCryptoError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("mailbox create failed")
        raise HTTPException(status_code=400, detail=f"Could not create mailbox: {exc}") from exc
    return {"ok": True, "mailbox": row}


@router.patch("/{mailbox_id}")
def update(
    mailbox_id: str,
    payload: MailboxUpdate,
    _: str = Depends(require_ceo),
) -> dict[str, Any]:
    _ensure_crypto()
    try:
        row = mailbox_registry.update_mailbox(
            mailbox_id,
            payload.model_dump(exclude_unset=True, exclude_none=True),
        )
    except MailboxCryptoError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("mailbox update failed")
        raise HTTPException(status_code=400, detail=f"Could not update mailbox: {exc}") from exc
    if not row:
        raise HTTPException(status_code=404, detail="mailbox not found")
    return {"ok": True, "mailbox": row}


@router.delete("/{mailbox_id}")
def delete(mailbox_id: str, _: str = Depends(require_ceo)) -> dict[str, bool]:
    """Soft-delete → status=disabled. Hard-delete via bulk admin only."""
    try:
        row = mailbox_registry.update_mailbox(mailbox_id, {"status": "disabled"})
    except Exception as exc:
        logger.exception("mailbox soft-delete failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="mailbox not found")
    return {"ok": True}


@router.post("/{mailbox_id}/test-connection")
def test_connection(mailbox_id: str, _: str = Depends(require_ceo)) -> dict[str, Any]:
    """Probe both SMTP + IMAP using stored creds. Never returns the password."""
    _ensure_crypto()
    smtp_result = test_smtp_login(mailbox_id)
    imap_result = mailbox_imap_poller.test_imap_login(mailbox_id)
    return {
        "ok": bool(smtp_result.get("ok")) and bool(imap_result.get("ok")),
        "smtp": smtp_result,
        "imap": imap_result,
    }


@router.post("/{mailbox_id}/pause")
def pause(mailbox_id: str, _: str = Depends(require_ceo)) -> dict[str, Any]:
    row = mailbox_registry.update_mailbox(mailbox_id, {"status": "paused"})
    if not row:
        raise HTTPException(status_code=404, detail="mailbox not found")
    return {"ok": True, "mailbox": row}


@router.post("/{mailbox_id}/resume")
def resume(mailbox_id: str, _: str = Depends(require_ceo)) -> dict[str, Any]:
    row = mailbox_registry.update_mailbox(mailbox_id, {"status": "active"})
    if not row:
        raise HTTPException(status_code=404, detail="mailbox not found")
    return {"ok": True, "mailbox": row}


@router.post("/{mailbox_id}/poll-replies")
def poll_replies(mailbox_id: str, _: str = Depends(require_ceo)) -> dict[str, Any]:
    """One-off IMAP reply poll for a single mailbox. Useful for debugging."""
    _ensure_crypto()
    return mailbox_imap_poller.run_imap_reply_poll([mailbox_id])


@router.post("/poll-replies")
def poll_all_replies(_: str = Depends(require_ceo)) -> dict[str, Any]:
    _ensure_crypto()
    return mailbox_imap_poller.run_imap_reply_poll()


@router.post("/bulk-import")
def bulk_import(payload: BulkImportPayload, uid: str = Depends(require_ceo)) -> dict[str, Any]:
    """Import several mailboxes in one go from either JSON ``rows`` or a CSV blob.

    CSV columns (header row required):
      email_address,display_name,domain,provider,
      smtp_host,smtp_port,smtp_username,smtp_password,smtp_use_tls,smtp_use_ssl,
      imap_host,imap_port,imap_username,imap_password,imap_use_ssl,
      daily_cap,vertical,notes
    """
    _ensure_crypto()
    rows_to_create: list[dict[str, Any]] = []
    if payload.rows:
        rows_to_create.extend(r.model_dump() for r in payload.rows)
    if payload.csv_text:
        reader = csv.DictReader(io.StringIO(payload.csv_text))
        for row in reader:
            clean = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
            for bool_field in ("smtp_use_tls", "smtp_use_ssl", "imap_use_ssl"):
                if bool_field in clean:
                    clean[bool_field] = str(clean[bool_field]).lower() in ("true", "1", "yes", "y")
            for int_field in ("smtp_port", "imap_port", "daily_cap"):
                if clean.get(int_field):
                    try:
                        clean[int_field] = int(clean[int_field])
                    except ValueError:
                        pass
            rows_to_create.append(clean)

    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in rows_to_create:
        try:
            row.setdefault("provider", "smtp")
            created.append(mailbox_registry.create_mailbox(row, created_by=uid))
        except Exception as exc:
            errors.append({"email": row.get("email_address"), "error": str(exc)[:400]})
    return {"ok": not errors, "created": created, "errors": errors, "count": len(created)}
