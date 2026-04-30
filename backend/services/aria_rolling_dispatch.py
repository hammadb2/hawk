"""ARIA Rolling Dispatcher — throttled email send.

Two caps stack on top of the per-mailbox daily cap from ``crm_mailboxes``:

  * ``DAILY_CAP_PER_VERTICAL`` (env ``ARIA_DAILY_CAP_PER_VERTICAL``,
    default 200): the most this dispatcher will send for a single
    vertical in a single calendar day, regardless of mailbox capacity.
  * ``DAILY_CAP_TOTAL`` (env ``ARIA_DAILY_CAP_TOTAL``, default 600): the
    aggregate daily ceiling across **all** verticals. Decoupled from the
    per-vertical cap so adding a new vertical doesn't silently raise the
    total send budget. The previous design implicitly tied the total to
    ``len(VERTICALS) * DAILY_CAP_PER_VERTICAL`` which silently 5x'd the
    ceiling when verticals expanded from 3 to 14.

Runs every hour 9am-4pm ET (8 ticks), each tick dispatches the per-vertical
catch-up quota so the daily total target is spread across US business
hours rather than blasted at 6:30am. Primary source is ``prospects``
rows where ``pipeline_status=ready`` (set by ``aria_post_scan_pipeline``),
ordered by ``hawk_score desc`` so higher-signal leads go out first.

v2 (Mailforge / native-SMTP) — Smartlead removed:
- Each send goes out via one of the rows in ``crm_mailboxes`` (round-robin by
  remaining daily capacity). Smartlead bulk upload is gone.
- Per-mailbox daily caps ``crm_mailboxes.daily_cap`` enforce the real inbox
  sending limits; the per-vertical 200/day quota is a coarser ceiling on top.
- Each prospect stores ``sent_via_mailbox_id`` + ``sent_message_id`` so the
  IMAP reply poller can thread replies back to the originating prospect.
- ``smartlead_campaign_id`` is no longer required to dispatch a prospect —
  the old gate blocked 800+ ready prospects indefinitely whenever the
  per-vertical campaign id wasn't seeded in ``crm_settings``.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from config import SUPABASE_URL
from services import mailbox_registry
from services.crm_bool_setting import fetch_crm_bool
from services.mailbox_smtp_sender import send_via_mailbox

logger = logging.getLogger(__name__)

# Dispatch runs on Eastern Time so emails land in US business hours.
# Per-state TZ routing is a v2 enhancement — for v1 we anchor to ET, which
# covers EST/CST comfortably and still lands before PT close-of-business.
DISPATCH_TZ = ZoneInfo("America/New_York")
# Backwards-compat alias (callers/tests may import ``MST``). Points to ET now.
MST = DISPATCH_TZ
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Per-vertical daily cap and the canonical tick schedule (9am–4pm ET inclusive = 8 ticks).
# Keep in sync with backend/main.py scheduler registration.
DAILY_CAP_PER_VERTICAL = int(os.environ.get("ARIA_DAILY_CAP_PER_VERTICAL", "200"))
# Aggregate ceiling across all verticals. Independent of vertical count so
# the dispatcher's total daily volume doesn't grow when verticals are added.
DAILY_CAP_TOTAL = int(os.environ.get("ARIA_DAILY_CAP_TOTAL", "600"))
DISPATCH_TICK_HOURS = [9, 10, 11, 12, 13, 14, 15, 16]
VERTICALS = (
    "dental",
    "legal",
    "accounting",
    "medical",
    "optometry",
    "chiropractic",
    "physical_therapy",
    "mental_health",
    "pharmacy",
    "real_estate",
    "financial_advisor",
    "insurance",
    "mortgage",
    "hr_payroll",
)


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _today_start_utc_iso() -> str:
    """Start-of-day in ET, rendered as UTC ISO for Supabase timestamptz filters."""
    now_local = datetime.now(DISPATCH_TZ)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc).isoformat()


def _remaining_ticks_today() -> int:
    """How many more dispatch ticks (inclusive of current one) are left today."""
    current_hour = datetime.now(DISPATCH_TZ).hour
    remaining = [h for h in DISPATCH_TICK_HOURS if h >= current_hour]
    return max(1, len(remaining))


def _count_sent_today(vertical: str) -> int:
    if not SUPABASE_URL:
        return 0
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers={**_sb_headers(), "Prefer": "count=exact"},
            params={
                "select": "id",
                "industry": f"eq.{vertical}",
                "dispatched_at": f"gte.{_today_start_utc_iso()}",
                "limit": "1",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        cr = r.headers.get("content-range", "")
        if "/" in cr:
            return int(cr.split("/", 1)[1])
    except Exception as exc:
        logger.warning("rolling-dispatch count sent_today vertical=%s failed: %s", vertical, exc)
    return 0


def _fetch_ready_prospects(vertical: str, limit: int) -> list[dict[str, Any]]:
    """Fetch ready-to-send prospects. Note: smartlead_campaign_id filter removed."""
    if not SUPABASE_URL or limit <= 0:
        return []
    params = {
        "select": (
            "id,domain,company_name,contact_email,contact_name,contact_title,"
            "email_subject,email_body,hawk_score,"
            "vulnerability_found,city,province,industry,stage,pipeline_status"
        ),
        "pipeline_status": "eq.ready",
        "industry": f"eq.{vertical}",
        "stage": "in.(new,scanning,scanned)",
        "contact_email": "not.is.null",
        "email_subject": "not.is.null",
        "email_body": "not.is.null",
        "order": "hawk_score.desc.nullslast,last_activity_at.asc",
        "limit": str(limit),
    }
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params=params,
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        logger.warning("rolling-dispatch fetch vertical=%s failed: %s", vertical, exc)
        return []


def _contact_display_name(prospect: dict[str, Any]) -> str:
    name = (prospect.get("contact_name") or "").strip()
    if name:
        return name
    return (prospect.get("company_name") or "").strip()


def _mark_prospect_dispatched(
    prospect_id: str,
    *,
    mailbox_id: str,
    message_id: str,
) -> bool:
    """Flip a single prospect to stage=sent_email + record the mailbox + message id.

    Stage-guarded PATCH so we never regress a row a rep already advanced.
    """
    if not SUPABASE_URL:
        return False
    now_iso = datetime.now(timezone.utc).isoformat()
    message_id_clean = message_id.strip("<> ").strip()
    domain = message_id_clean.split("@", 1)[1] if "@" in message_id_clean else None
    patch: dict[str, Any] = {
        "stage": "sent_email",
        "pipeline_status": "dispatched",
        "dispatched_at": now_iso,
        "last_activity_at": now_iso,
        "sent_via_mailbox_id": mailbox_id,
        "sent_message_id": message_id_clean,
    }
    if domain:
        patch["sent_message_id_domain"] = domain
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb_headers(),
            params={
                "id": f"eq.{prospect_id}",
                "stage": "in.(new,scanning,scanned)",
                "pipeline_status": "eq.ready",
            },
            json=patch,
            timeout=15.0,
        )
        r.raise_for_status()
        return bool(r.json() or [])
    except Exception as exc:
        logger.warning("rolling-dispatch mark-dispatched %s failed: %s", prospect_id, exc)
        return False


def _quota_for_tick(vertical: str) -> tuple[int, int, int]:
    """Returns (sent_today, remaining_today, quota_for_this_tick)."""
    sent = _count_sent_today(vertical)
    remaining = max(0, DAILY_CAP_PER_VERTICAL - sent)
    if remaining == 0:
        return sent, 0, 0
    ticks_left = _remaining_ticks_today()
    per_tick = math.ceil(remaining / ticks_left)
    return sent, remaining, min(per_tick, remaining)


def _dispatch_prospect(prospect: dict[str, Any], vertical: str) -> dict[str, Any]:
    """Pick a mailbox + send + mark. Returns an outcome dict for the per-vertical stats."""
    mailbox = mailbox_registry.pick_next_for_vertical(vertical)
    if not mailbox:
        return {"ok": False, "reason": "no_active_mailbox"}

    mailbox_id = str(mailbox["id"])
    result = send_via_mailbox(
        mailbox_id,
        to_email=str(prospect.get("contact_email") or ""),
        to_name=_contact_display_name(prospect),
        subject=str(prospect.get("email_subject") or ""),
        body_text=str(prospect.get("email_body") or ""),
        reply_to=None,
    )
    if not result.ok or not result.message_id:
        return {
            "ok": False,
            "mailbox_id": mailbox_id,
            "error": result.error or "unknown send error",
            "was_bounce": result.was_bounce,
            "was_auth_failure": result.was_auth_failure,
        }

    marked = _mark_prospect_dispatched(
        str(prospect["id"]),
        mailbox_id=mailbox_id,
        message_id=result.message_id,
    )
    return {
        "ok": True,
        "mailbox_id": mailbox_id,
        "message_id": result.message_id,
        "marked": marked,
    }


def run_rolling_dispatch() -> dict[str, Any]:
    """Public entrypoint. Safe to invoke manually outside tick hours."""
    start = datetime.now(timezone.utc)
    stats: dict[str, Any] = {
        "ok": True,
        "dispatched_total": 0,
        "by_vertical": {},
        "duration_seconds": 0,
    }
    if not SUPABASE_URL or not SERVICE_KEY:
        return {**stats, "ok": False, "reason": "supabase not configured"}

    # Global kill switch + mailbox-dispatch feature flag.
    from services.aria_morning_dispatch import _get_setting

    enabled = _get_setting("pipeline_dispatch_enabled", "true")
    if enabled.lower() not in ("true", "1", "yes"):
        return {**stats, "ok": False, "skipped": True, "reason": "pipeline_dispatch_enabled is false"}
    mbx_on = _get_setting("mailbox_dispatch_enabled", "true")
    if mbx_on.lower() not in ("true", "1", "yes"):
        return {**stats, "ok": False, "skipped": True, "reason": "mailbox_dispatch_enabled is false"}

    # Pre-flight: do we have any active mailboxes at all? If not, bail clean.
    active_mailboxes = mailbox_registry.list_mailboxes(status="active")
    if not active_mailboxes:
        return {
            **stats,
            "ok": False,
            "skipped": True,
            "reason": "no_active_mailboxes",
            "fix": "add mailboxes at /crm/settings/mailboxes",
        }

    # Global daily cap: pre-compute the budget left across all verticals so
    # adding a vertical doesn't silently raise the total send ceiling.
    sent_total_today = sum(_count_sent_today(v) for v in VERTICALS)
    global_remaining = max(0, DAILY_CAP_TOTAL - sent_total_today)
    stats["global"] = {
        "daily_cap_total": DAILY_CAP_TOTAL,
        "sent_total_today": sent_total_today,
        "remaining_total": global_remaining,
    }

    for vertical in VERTICALS:
        sent_today, remaining_today, quota = _quota_for_tick(vertical)
        # Clamp the per-vertical tick quota by what's left of the global
        # daily budget. Once the global budget is spent, all remaining
        # verticals get quota=0 for this tick.
        quota = min(quota, global_remaining)
        if quota <= 0:
            stats["by_vertical"][vertical] = {
                "sent_today": sent_today,
                "remaining_today": remaining_today,
                "quota": 0,
                "sent": 0,
                "reason": "global_cap_reached" if global_remaining <= 0 else None,
            }
            continue

        prospects = _fetch_ready_prospects(vertical, quota)
        if not prospects:
            stats["by_vertical"][vertical] = {
                "sent_today": sent_today,
                "remaining_today": remaining_today,
                "quota": quota,
                "sent": 0,
                "reason": "no ready prospects",
            }
            continue

        sent = 0
        failed = 0
        bounced = 0
        auth_failed = 0
        capacity_exhausted = False
        error_samples: list[str] = []
        for prospect in prospects:
            outcome = _dispatch_prospect(prospect, vertical)
            if outcome.get("ok"):
                sent += 1
                global_remaining -= 1
                continue
            failed += 1
            if outcome.get("reason") == "no_active_mailbox":
                capacity_exhausted = True
                # Stop the per-vertical tick early — we'll retry these prospects
                # next tick once a mailbox rolls over or becomes available.
                break
            if outcome.get("was_bounce"):
                bounced += 1
            if outcome.get("was_auth_failure"):
                auth_failed += 1
            err = str(outcome.get("error") or "")
            if err and len(error_samples) < 3:
                error_samples.append(err[:200])

        stats["by_vertical"][vertical] = {
            "sent_today": sent_today + sent,
            "remaining_today": max(0, remaining_today - sent),
            "quota": quota,
            "sent": sent,
            "failed": failed,
            "bounced": bounced,
            "auth_failed": auth_failed,
            "capacity_exhausted": capacity_exhausted,
            "errors_sample": error_samples,
        }
        stats["dispatched_total"] += sent

    # Route overflow to VA queue after the last tick of the day (4pm ET).
    current_hour = datetime.now(DISPATCH_TZ).hour
    if current_hour >= DISPATCH_TICK_HOURS[-1]:
        va_routed = _route_overflow_to_va_queue()
        stats["va_queue_routed"] = va_routed

    stats["duration_seconds"] = int((datetime.now(timezone.utc) - start).total_seconds())
    logger.info("rolling-dispatch complete: %s", json.dumps(stats))
    return stats


def _route_overflow_to_va_queue() -> dict[str, int]:
    """Move ``ready`` prospects past the daily automated-dispatch cap into the
    VA queue so manual outreach can pick them up.

    Called at the end of the final dispatch tick of the day. Safe to call
    repeatedly — it only targets ``pipeline_status=ready`` rows.
    """
    out: dict[str, int] = {}
    if not fetch_crm_bool("va_queue_enabled", default=True):
        return out
    if not SUPABASE_URL or not SERVICE_KEY:
        return out

    for vertical in VERTICALS:
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers={**_sb_headers(), "Prefer": "count=exact"},
                params={
                    "select": "id",
                    "pipeline_status": "eq.ready",
                    "industry": f"eq.{vertical}",
                    "limit": "1",
                },
                timeout=15.0,
            )
            r.raise_for_status()
            cr = r.headers.get("content-range", "")
            ready_count = int(cr.split("/", 1)[1]) if "/" in cr else 0
        except Exception as exc:
            logger.warning("va-overflow count vertical=%s failed: %s", vertical, exc)
            continue

        if ready_count == 0:
            out[vertical] = 0
            continue

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            r = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/prospects",
                headers=_sb_headers(),
                params={
                    "pipeline_status": "eq.ready",
                    "industry": f"eq.{vertical}",
                    "stage": "in.(new,scanning,scanned)",
                },
                json={
                    "pipeline_status": "va_queue",
                    "last_activity_at": now_iso,
                },
                timeout=30.0,
            )
            r.raise_for_status()
            try:
                routed = len(r.json() or [])
            except Exception:
                routed = 0
            out[vertical] = routed
            logger.info("va-overflow routed vertical=%s count=%d", vertical, routed)
        except Exception as exc:
            logger.warning("va-overflow route vertical=%s failed: %s", vertical, exc)
    return out
