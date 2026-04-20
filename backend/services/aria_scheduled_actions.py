"""Registry + executor for ARIA's time-fused follow-ups.

Any flow that says "come back and do this at time T" goes through this file:
 * 48-hour follow-up after a positive reply that didn't convert
 * 24-hour reminder before a booked Cal.com call
 * Weekly nurture drip (30 days)
 * OOO return-date follow-up
 * 90-day snooze re-engagement

The table is ``aria_scheduled_actions``. Scheduler job runs every 5 minutes,
claims rows where ``due_at <= now()`` and ``status = 'pending'``, dispatches
them to a handler keyed on ``action_type``. Handlers are idempotent.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from config import SUPABASE_URL

logger = logging.getLogger(__name__)

_SUPABASE_REST = f"{SUPABASE_URL}/rest/v1/aria_scheduled_actions" if SUPABASE_URL else ""


def _sb_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


# ── Scheduling API ────────────────────────────────────────────────────────


def schedule(
    *,
    action_type: str,
    due_at: datetime,
    prospect_id: str | None = None,
    inbound_reply_id: str | None = None,
    payload: dict[str, Any] | None = None,
    dedupe: bool = True,
) -> str | None:
    """Insert a row in ``aria_scheduled_actions``. Returns the new row id.

    When ``dedupe=True`` (default) and a pending row already exists for the
    same (prospect_id, action_type), we skip the insert and return the
    existing row's id — prevents double-scheduling when a webhook fires
    multiple times.
    """
    if not _SUPABASE_REST or not action_type:
        return None

    if dedupe and prospect_id:
        existing = _find_pending(prospect_id, action_type)
        if existing:
            return str(existing.get("id"))

    row = {
        "action_type": action_type,
        "due_at": due_at.astimezone(timezone.utc).isoformat(),
        "payload": payload or {},
        "status": "pending",
    }
    if prospect_id:
        row["prospect_id"] = prospect_id
    if inbound_reply_id:
        row["inbound_reply_id"] = inbound_reply_id

    try:
        r = httpx.post(
            _SUPABASE_REST,
            headers={**_sb_headers(), "Prefer": "return=representation"},
            json=row,
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return str(data[0].get("id"))
        if isinstance(data, dict):
            return str(data.get("id"))
    except Exception:
        logger.exception(
            "schedule(%s) failed prospect=%s due=%s", action_type, prospect_id, due_at
        )
    return None


def cancel_pending(prospect_id: str, action_types: list[str] | None = None) -> int:
    """Mark pending rows for this prospect (optionally filtered by action_type) as cancelled."""
    if not _SUPABASE_REST or not prospect_id:
        return 0
    params = {
        "prospect_id": f"eq.{prospect_id}",
        "status": "eq.pending",
    }
    if action_types:
        params["action_type"] = "in.(" + ",".join(action_types) + ")"
    try:
        r = httpx.patch(
            _SUPABASE_REST,
            headers={**_sb_headers(), "Prefer": "return=representation"},
            params=params,
            json={"status": "cancelled", "completed_at": datetime.now(timezone.utc).isoformat()},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        return len(data) if isinstance(data, list) else 0
    except Exception:
        logger.exception("cancel_pending failed prospect=%s", prospect_id)
        return 0


def _find_pending(prospect_id: str, action_type: str) -> dict[str, Any] | None:
    try:
        r = httpx.get(
            _SUPABASE_REST,
            headers=_sb_headers(),
            params={
                "prospect_id": f"eq.{prospect_id}",
                "action_type": f"eq.{action_type}",
                "status": "eq.pending",
                "select": "id",
                "limit": "1",
            },
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception:
        return None


# ── Executor ──────────────────────────────────────────────────────────────


# Populated by register_handler; keeps this module importable without circular deps.
_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_handler(action_type: str, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    _HANDLERS[action_type] = handler


def _mark(row_id: str, *, status: str, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    body = {
        "status": status,
        "last_attempt_at": now,
    }
    if status == "done":
        body["completed_at"] = now
    if error:
        body["last_error"] = error[:1500]
    try:
        httpx.patch(
            _SUPABASE_REST,
            headers=_sb_headers(),
            params={"id": f"eq.{row_id}"},
            json=body,
            timeout=10.0,
        ).raise_for_status()
    except Exception:
        logger.exception("scheduled_actions._mark failed id=%s status=%s", row_id, status)


def _claim_due(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch + mark rows as in_flight so two scheduler ticks never race."""
    if not _SUPABASE_REST:
        return []
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        r = httpx.get(
            _SUPABASE_REST,
            headers=_sb_headers(),
            params={
                "status": "eq.pending",
                "due_at": f"lte.{now_iso}",
                "order": "due_at.asc",
                "limit": str(limit),
                "select": "*",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        pending = r.json() if isinstance(r.json(), list) else []
    except Exception:
        logger.exception("scheduled_actions._claim_due query failed")
        return []

    claimed: list[dict[str, Any]] = []
    for row in pending:
        rid = row.get("id")
        if not rid:
            continue
        try:
            patch = httpx.patch(
                _SUPABASE_REST,
                headers={**_sb_headers(), "Prefer": "return=representation"},
                params={"id": f"eq.{rid}", "status": "eq.pending"},
                json={
                    "status": "in_flight",
                    "attempts": int(row.get("attempts") or 0) + 1,
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
            patch.raise_for_status()
            got = patch.json()
            if isinstance(got, list) and got:
                claimed.append(got[0])
        except Exception:
            logger.exception("scheduled_actions: claim failed id=%s", rid)
    return claimed


def run_due_actions(batch: int = 50) -> dict[str, Any]:
    """Scheduler entrypoint — run once per tick."""
    claimed = _claim_due(limit=batch)
    done = 0
    failed = 0
    errors: list[str] = []
    for row in claimed:
        action = row.get("action_type") or ""
        handler = _HANDLERS.get(action)
        if not handler:
            _mark(str(row["id"]), status="failed", error=f"no handler for {action}")
            failed += 1
            errors.append(f"no handler: {action}")
            continue
        try:
            handler(row)
            _mark(str(row["id"]), status="done")
            done += 1
        except Exception as exc:
            logger.exception("scheduled_action handler raised action=%s id=%s", action, row.get("id"))
            attempts = int(row.get("attempts") or 0)
            # 3 retries, then permanently fail.
            new_status = "failed" if attempts >= 3 else "pending"
            _mark(str(row["id"]), status=new_status, error=str(exc))
            if new_status == "failed":
                failed += 1
                errors.append(f"{action}: {exc!s}"[:200])

    return {
        "claimed": len(claimed),
        "done": done,
        "failed": failed,
        "errors": errors[:10],
    }


__all__ = [
    "schedule",
    "cancel_pending",
    "register_handler",
    "run_due_actions",
]
