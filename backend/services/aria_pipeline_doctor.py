"""ARIA Pipeline Doctor — autonomous outbound pipeline health monitor + auto-fixer.

Scans every stage of the outbound pipeline (``new`` → ``scanning`` → ``scanned``
→ ``ready`` → ``contacted`` → ``dispatched``) every ~15 minutes, diagnoses
where prospects are getting stuck, and auto-applies the safest escape hatch
for each stuck bucket so we never sit on a queue of leads that *could* have
gone out today.

Design principles:

* **Autonomous.** Each bucket has a `fix` callable that ARIA will invoke
  without waiting for human approval. Fixes are idempotent — re-running them
  is cheaper than skipping a potential email.
* **Escape hatches only.** Fixes do not synthesise contacts or bypass the
  verified-email gate (Apollo's ``verified``/``likely to engage`` filter).
  They trigger backfills, retry soft failures, clear orphaned watchdog state,
  and nudge the rolling dispatcher.
* **Surface everywhere.** Returns a structured snapshot the CEO dashboard,
  CRM AI Command Center, and the CEO SMS escalation all read from so ``ARIA,
  why is the pipeline stuck?`` and the dashboard card always agree.
* **Never silently drop.** Anything the Doctor cannot auto-resolve escalates
  via ``send_ceo_sms`` if it crosses ``CEO_SMS_THRESHOLD``.

Buckets the Doctor understands today:

* ``new`` prospects > 10 min old with no ``active_scan_job_id`` — the SLA
  auto-scan should have claimed them. Fix: trigger the SLA job.
* ``scanning`` prospects with ``active_scan_job_id`` older than
  ``SLA_SCAN_WATCHDOG_MIN`` — orphaned scan. Fix: release the watchdog (same
  code the SLA job runs on every tick).
* ``scanned`` prospects older than 3 min with missing ``contact_email`` or
  ``email_subject`` or ``smartlead_campaign_id`` — post-scan never finished.
  Fix: enqueue them through ``run_post_scan_sync`` (chunked + parallel).
* ``ready`` prospects older than 90 min during tick hours that still have
  ``pipeline_status='ready'`` — rolling dispatcher didn't pick them up. Fix:
  call ``run_rolling_dispatch()`` directly.
* Apollo credit exhaustion — if ``credits_remaining_today() < 50`` but
  ``apollo_daily_credit_cap`` < hard ceiling, bump the cap.
* ``suppressions`` created in the last 24 h with reason
  ``post_scan:zerobounce_*`` — the new ZB-disabled pipeline would have let
  them through. Fix: re-enqueue for post-scan (Apollo-only path).

Every snapshot is written to the ``aria_pipeline_health_log`` column of
``crm_settings`` (key ``aria_pipeline_doctor_last_snapshot``) so the CEO
dashboard can render the latest run without triggering a fresh diagnosis.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from config import SUPABASE_URL

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Thresholds — override via env on Railway without a deploy.
STUCK_NEW_MIN = int(os.environ.get("DOCTOR_STUCK_NEW_MIN", "10"))
STUCK_SCANNING_MIN = int(os.environ.get("DOCTOR_STUCK_SCANNING_MIN", "15"))
STUCK_SCANNED_MIN = int(os.environ.get("DOCTOR_STUCK_SCANNED_MIN", "5"))
STUCK_READY_MIN = int(os.environ.get("DOCTOR_STUCK_READY_MIN", "90"))
CEO_SMS_THRESHOLD = int(os.environ.get("DOCTOR_CEO_SMS_THRESHOLD", "100"))
APOLLO_CAP_CEILING = int(os.environ.get("APOLLO_CAP_HARD_CEILING", "8000"))
APOLLO_CAP_BUMP = int(os.environ.get("APOLLO_CAP_BUMP", "1000"))
BACKFILL_MAX_PER_RUN = int(os.environ.get("DOCTOR_BACKFILL_MAX", "250"))
BACKFILL_CONCURRENCY = int(os.environ.get("DOCTOR_BACKFILL_CONCURRENCY", "10"))
SETTINGS_SNAPSHOT_KEY = "aria_pipeline_doctor_last_snapshot"


def _sb_headers(*, prefer: str = "return=minimal") -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _configured() -> bool:
    return bool(SUPABASE_URL and SERVICE_KEY)


def _count(table: str, filters: dict[str, str]) -> int:
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={**_sb_headers(), "Prefer": "count=exact"},
            params={**filters, "select": "id", "limit": "0"},
            timeout=15.0,
        )
        cr = r.headers.get("content-range", "")
        if "/" in cr:
            try:
                return int(cr.split("/")[1])
            except (ValueError, IndexError):
                return 0
        return 0
    except Exception as exc:
        logger.warning("doctor count %s failed: %s", table, exc)
        return 0


def _fetch(table: str, filters: dict[str, str]) -> list[dict[str, Any]]:
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_sb_headers(),
            params=filters,
            timeout=20.0,
        )
        r.raise_for_status()
        return list(r.json() or [])
    except Exception as exc:
        logger.warning("doctor fetch %s failed: %s", table, exc)
        return []


# ── Diagnosis ────────────────────────────────────────────────────────────────


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _diagnose_new_backlog() -> dict[str, Any]:
    cutoff = _now() - timedelta(minutes=STUCK_NEW_MIN)
    count = _count(
        "prospects",
        {
            "stage": "eq.new",
            "active_scan_job_id": "is.null",
            "scanned_at": "is.null",
            "created_at": f"lt.{_iso(cutoff)}",
        },
    )
    return {
        "bucket": "new_backlog",
        "stuck": count,
        "threshold_minutes": STUCK_NEW_MIN,
        "severity": "warn" if count > 50 else "info",
        "diagnosis": (
            f"{count} prospects stuck in stage=new past the {STUCK_NEW_MIN}-min SLA. "
            "The SLA auto-scan should have claimed them — either the scheduler skipped "
            "a tick, APIFY_TOKEN is missing, or SLA_SCAN_BATCH is too small."
        )
        if count
        else None,
    }


def _diagnose_scanning_orphans() -> dict[str, Any]:
    watchdog_min = int(os.environ.get("SLA_SCAN_WATCHDOG_MIN", "15"))
    cutoff = _now() - timedelta(minutes=watchdog_min)
    count = _count(
        "prospects",
        {
            "stage": "eq.scanning",
            "active_scan_job_id": "not.is.null",
            "scan_started_at": f"lt.{_iso(cutoff)}",
        },
    )
    return {
        "bucket": "scanning_orphans",
        "stuck": count,
        "threshold_minutes": watchdog_min,
        "severity": "warn" if count else "info",
        "diagnosis": (
            f"{count} prospects have been in stage=scanning for > {watchdog_min} min with "
            "a live active_scan_job_id. The scanner crashed or the network blipped; the "
            "watchdog needs to release them so the SLA job can re-claim."
        )
        if count
        else None,
    }


def _diagnose_scanned_backlog() -> dict[str, Any]:
    cutoff = _now() - timedelta(minutes=STUCK_SCANNED_MIN)
    # Use OR so we catch every flavour of incomplete post-scan state.
    filters = {
        "stage": "eq.scanned",
        "pipeline_status": "eq.scanned",
        "scanned_at": f"lt.{_iso(cutoff)}",
        "or": (
            "(contact_email.is.null,"
            "email_subject.is.null,"
            "smartlead_campaign_id.is.null)"
        ),
    }
    count = _count("prospects", filters)
    return {
        "bucket": "scanned_backlog",
        "stuck": count,
        "threshold_minutes": STUCK_SCANNED_MIN,
        "severity": "critical" if count >= CEO_SMS_THRESHOLD else "warn" if count else "info",
        "diagnosis": (
            f"{count} prospects finished scanning but never completed post-scan enrichment "
            "(missing contact_email, email_subject, or smartlead_campaign_id). Likely caused "
            "by a finalize fire-and-forget that never landed, or a pre-unlock Apollo run."
        )
        if count
        else None,
    }


def _diagnose_ready_backlog() -> dict[str, Any]:
    cutoff = _now() - timedelta(minutes=STUCK_READY_MIN)
    count = _count(
        "prospects",
        {
            "pipeline_status": "eq.ready",
            "stage": "in.(new,scanning,scanned)",
            "last_activity_at": f"lt.{_iso(cutoff)}",
        },
    )
    return {
        "bucket": "ready_backlog",
        "stuck": count,
        "threshold_minutes": STUCK_READY_MIN,
        "severity": "warn" if count else "info",
        "diagnosis": (
            f"{count} prospects are pipeline_status=ready but haven't been dispatched in "
            f"> {STUCK_READY_MIN} min. Rolling dispatcher may have hit Smartlead quota or "
            "the pipeline_dispatch_enabled kill switch is off."
        )
        if count
        else None,
    }


def _diagnose_apollo_credits() -> dict[str, Any]:
    try:
        from services.apollo_enrichment import credits_remaining_today
    except Exception as exc:  # pragma: no cover — defensive import
        return {
            "bucket": "apollo_credits",
            "stuck": 0,
            "severity": "info",
            "diagnosis": f"Apollo credit check unavailable: {exc}",
        }
    remaining = credits_remaining_today()
    cap_raw = _fetch(
        "crm_settings", {"key": "eq.apollo_daily_credit_cap", "select": "value", "limit": "1"}
    )
    try:
        cap = int((cap_raw[0] or {}).get("value") or "2500") if cap_raw else 2500
    except (ValueError, TypeError):
        cap = 2500
    severity = "critical" if remaining <= 0 else "warn" if remaining < 100 else "info"
    return {
        "bucket": "apollo_credits",
        "stuck": max(0, 100 - remaining) if remaining < 100 else 0,
        "remaining": remaining,
        "cap": cap,
        "severity": severity,
        "diagnosis": (
            f"Apollo credits: {remaining}/{cap} remaining today."
            + (
                " Cap hit — enrichment returning None, every post-scan will soft-drop."
                if remaining <= 0
                else " Close to cap — enrichment will stop soon."
                if remaining < 100
                else ""
            )
        ),
    }


def _diagnose_recent_zb_softdrops() -> dict[str, Any]:
    """Legacy ZeroBounce soft-drops that the Apollo-only pipeline would keep."""
    cutoff = _now() - timedelta(hours=24)
    rows = _fetch(
        "suppressions",
        {
            "select": "domain,reason,created_at",
            "reason": "like.post_scan:zerobounce_*",
            "created_at": f"gte.{_iso(cutoff)}",
            "limit": "500",
        },
    )
    return {
        "bucket": "legacy_zerobounce_softdrops",
        "stuck": len(rows),
        "severity": "warn" if rows else "info",
        "sample_domains": [r.get("domain") for r in rows[:10]],
        "diagnosis": (
            f"{len(rows)} domains soft-dropped in the last 24h for ZeroBounce status codes. "
            "The pipeline now treats ZB as opt-in (Apollo's verified-only filter is the gate), "
            "so these prospects could have gone out. Recover via suppressions review."
        )
        if rows
        else None,
    }


# ── Auto-fixes ───────────────────────────────────────────────────────────────


def _fix_new_backlog() -> dict[str, Any]:
    try:
        from services.aria_sla_auto_scan import run_sla_auto_scan

        out = run_sla_auto_scan()
        return {"applied": True, "detail": out}
    except Exception as exc:
        logger.exception("doctor fix new_backlog failed")
        return {"applied": False, "error": str(exc)[:400]}


def _fix_scanning_orphans() -> dict[str, Any]:
    try:
        from services.aria_sla_auto_scan import _watchdog_release_stuck_jobs  # type: ignore[attr-defined]

        released = _watchdog_release_stuck_jobs()
        return {"applied": True, "released": released}
    except Exception as exc:
        logger.exception("doctor fix scanning_orphans failed")
        return {"applied": False, "error": str(exc)[:400]}


def _fix_scanned_backlog() -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    cutoff = _now() - timedelta(minutes=STUCK_SCANNED_MIN)
    prospects = _fetch(
        "prospects",
        {
            "select": "id,domain",
            "stage": "eq.scanned",
            "pipeline_status": "eq.scanned",
            "scanned_at": f"lt.{_iso(cutoff)}",
            "or": (
                "(contact_email.is.null,"
                "email_subject.is.null,"
                "smartlead_campaign_id.is.null)"
            ),
            "order": "scanned_at.asc",
            "limit": str(BACKFILL_MAX_PER_RUN),
        },
    )
    if not prospects:
        return {"applied": True, "processed": 0}

    from services.aria_post_scan_pipeline import run_post_scan_sync

    outcomes: dict[str, int] = {}

    def _one(p: dict[str, Any]) -> dict[str, Any]:
        try:
            return run_post_scan_sync(p["id"]) or {"ok": False, "outcome": "empty"}
        except Exception as exc:
            return {"ok": False, "outcome": "error", "error": str(exc)[:200]}

    with ThreadPoolExecutor(max_workers=BACKFILL_CONCURRENCY) as pool:
        for res in pool.map(_one, prospects):
            key = str(res.get("outcome") or "unknown")
            outcomes[key] = outcomes.get(key, 0) + 1
    return {
        "applied": True,
        "processed": len(prospects),
        "outcomes": outcomes,
    }


def _fix_ready_backlog() -> dict[str, Any]:
    try:
        from services.aria_rolling_dispatch import run_rolling_dispatch

        out = run_rolling_dispatch()
        return {"applied": True, "detail": out}
    except Exception as exc:
        logger.exception("doctor fix ready_backlog failed")
        return {"applied": False, "error": str(exc)[:400]}


def _fix_apollo_credits() -> dict[str, Any]:
    cap_rows = _fetch(
        "crm_settings", {"key": "eq.apollo_daily_credit_cap", "select": "value", "limit": "1"}
    )
    try:
        current = int((cap_rows[0] or {}).get("value") or "2500") if cap_rows else 2500
    except (ValueError, TypeError):
        current = 2500
    if current >= APOLLO_CAP_CEILING:
        return {
            "applied": False,
            "reason": f"cap {current} already at/above ceiling {APOLLO_CAP_CEILING}",
        }
    new_cap = min(APOLLO_CAP_CEILING, current + APOLLO_CAP_BUMP)
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers=_sb_headers(),
            params={"key": "eq.apollo_daily_credit_cap"},
            json={"value": str(new_cap)},
            timeout=15.0,
        )
        return {"applied": True, "old_cap": current, "new_cap": new_cap}
    except Exception as exc:
        return {"applied": False, "error": str(exc)[:400]}


def _fix_noop() -> dict[str, Any]:
    return {"applied": False, "reason": "no autonomous fix; review manually"}


# ── Mailbox health diagnosers / fixes (native-SMTP dispatcher) ───────────────


def _count_ready_prospects() -> int:
    if not SUPABASE_URL:
        return 0
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers={**_sb_headers(), "Prefer": "count=exact"},
            params={"select": "id", "pipeline_status": "eq.ready", "limit": "1"},
            timeout=15.0,
        )
        r.raise_for_status()
        cr = r.headers.get("content-range", "")
        return int(cr.split("/", 1)[1]) if "/" in cr else 0
    except Exception:
        return 0


def _diagnose_no_active_mailboxes() -> dict[str, Any]:
    """No active mailboxes at all → 100% of ready prospects are blocked."""
    try:
        from services import mailbox_registry

        active = mailbox_registry.list_mailboxes(status="active")
    except Exception as exc:
        return {
            "bucket": "no_active_mailboxes",
            "stuck": 0,
            "severity": "info",
            "diagnosis": f"mailbox registry unreachable: {exc}",
            "recommendation": "check MAILBOX_ENCRYPTION_KEY + crm_mailboxes table",
        }
    if active:
        return {
            "bucket": "no_active_mailboxes",
            "stuck": 0,
            "severity": "ok",
            "diagnosis": f"{len(active)} active mailbox(es) ready to send",
        }
    ready = _count_ready_prospects()
    severity = "critical" if ready else "warn"
    return {
        "bucket": "no_active_mailboxes",
        "stuck": ready,
        "severity": severity,
        "diagnosis": (
            f"{ready} prospects at pipeline_status=ready but no crm_mailboxes.status=active rows. "
            "Rolling dispatcher cannot send anything."
        ),
        "recommendation": "add or reactivate a mailbox at /crm/settings/mailboxes",
    }


def _diagnose_mailbox_caps_exhausted() -> dict[str, Any]:
    """All active mailboxes have sent_today >= daily_cap."""
    try:
        from services import mailbox_registry

        active = mailbox_registry.list_mailboxes(status="active")
    except Exception as exc:
        return {
            "bucket": "mailbox_caps_exhausted",
            "stuck": 0,
            "severity": "info",
            "diagnosis": f"mailbox registry unreachable: {exc}",
        }
    if not active:
        return {
            "bucket": "mailbox_caps_exhausted",
            "stuck": 0,
            "severity": "ok",
            "diagnosis": "no active mailboxes (covered by no_active_mailboxes bucket)",
        }
    today = datetime.now(timezone.utc).date().isoformat()
    remaining = 0
    for mbx in active:
        cap = int(mbx.get("daily_cap") or 0)
        date = str(mbx.get("sent_today_date") or "")
        sent = int(mbx.get("sent_today") or 0) if date == today else 0
        remaining += max(0, cap - sent)
    if remaining > 0:
        return {
            "bucket": "mailbox_caps_exhausted",
            "stuck": 0,
            "severity": "ok",
            "diagnosis": f"{remaining} sends remaining today across {len(active)} mailbox(es)",
        }
    ready = _count_ready_prospects()
    severity = "warn" if ready < 50 else "critical"
    return {
        "bucket": "mailbox_caps_exhausted",
        "stuck": ready,
        "severity": severity,
        "diagnosis": (
            f"all {len(active)} active mailboxes at/over daily_cap; "
            f"{ready} prospects waiting — rolls over at midnight MST"
        ),
        "recommendation": "raise daily_cap on mailboxes or add more inboxes via /crm/settings/mailboxes",
    }


def _diagnose_mailbox_high_bounce() -> dict[str, Any]:
    """Any active mailbox whose 7-day bounce_rate exceeds the threshold."""
    try:
        from services import mailbox_registry

        all_mbx = mailbox_registry.list_mailboxes()
    except Exception as exc:
        return {
            "bucket": "mailbox_high_bounce",
            "stuck": 0,
            "severity": "info",
            "diagnosis": f"mailbox registry unreachable: {exc}",
        }
    threshold_rows = _fetch(
        "crm_settings",
        {"key": "eq.mailbox_bounce_rate_threshold", "select": "value", "limit": "1"},
    )
    try:
        threshold = float((threshold_rows[0] or {}).get("value") or 0.05) if threshold_rows else 0.05
    except (ValueError, TypeError):
        threshold = 0.05

    hot: list[dict[str, Any]] = []
    for mbx in all_mbx:
        if str(mbx.get("status")) != "active":
            continue
        try:
            rate = float(mbx.get("bounce_rate_7d") or 0)
        except (ValueError, TypeError):
            rate = 0.0
        if rate >= threshold:
            hot.append(
                {
                    "id": str(mbx.get("id")),
                    "email_address": mbx.get("email_address"),
                    "bounce_rate_7d": rate,
                    "bounce_count_7d": int(mbx.get("bounce_count_7d") or 0),
                    "sent_count_7d": int(mbx.get("sent_count_7d") or 0),
                }
            )

    if not hot:
        return {
            "bucket": "mailbox_high_bounce",
            "stuck": 0,
            "severity": "ok",
            "diagnosis": f"no active mailbox is over {int(threshold * 100)}% bounce rate",
        }
    return {
        "bucket": "mailbox_high_bounce",
        "stuck": len(hot),
        "severity": "critical",
        "diagnosis": (
            f"{len(hot)} mailbox(es) above {int(threshold * 100)}% 7-day bounce rate — "
            "deliverability risk, auto-pausing"
        ),
        "recommendation": "investigate warmup / content / domain reputation before reactivating",
        "mailboxes": hot,
    }


def _fix_mailbox_high_bounce() -> dict[str, Any]:
    """Auto-pause every mailbox currently over the bounce-rate threshold."""
    try:
        from services import mailbox_registry
    except Exception as exc:
        return {"applied": False, "error": f"mailbox registry unavailable: {exc}"}

    threshold_rows = _fetch(
        "crm_settings",
        {"key": "eq.mailbox_bounce_rate_threshold", "select": "value", "limit": "1"},
    )
    try:
        threshold = float((threshold_rows[0] or {}).get("value") or 0.05) if threshold_rows else 0.05
    except (ValueError, TypeError):
        threshold = 0.05

    paused: list[str] = []
    errors: list[str] = []
    for mbx in mailbox_registry.list_mailboxes(status="active"):
        try:
            rate = float(mbx.get("bounce_rate_7d") or 0)
        except (ValueError, TypeError):
            rate = 0.0
        if rate < threshold:
            continue
        try:
            mailbox_registry.update_mailbox(str(mbx["id"]), {"status": "paused"})
            paused.append(str(mbx.get("email_address") or mbx["id"]))
        except Exception as exc:
            errors.append(f"{mbx.get('email_address')}: {exc}")
    return {
        "applied": bool(paused),
        "paused": paused,
        "errors": errors,
        "threshold": threshold,
    }


FIXES: dict[str, Callable[[], dict[str, Any]]] = {
    "new_backlog": _fix_new_backlog,
    "scanning_orphans": _fix_scanning_orphans,
    "scanned_backlog": _fix_scanned_backlog,
    "ready_backlog": _fix_ready_backlog,
    "apollo_credits": _fix_apollo_credits,
    "legacy_zerobounce_softdrops": _fix_noop,
    "no_active_mailboxes": _fix_noop,
    "mailbox_caps_exhausted": _fix_noop,
    "mailbox_high_bounce": _fix_mailbox_high_bounce,
}


# ── Snapshot persistence ─────────────────────────────────────────────────────


def _persist_snapshot(snapshot: dict[str, Any]) -> None:
    if not _configured():
        return
    payload = {"key": SETTINGS_SNAPSHOT_KEY, "value": json.dumps(snapshot)[:60000]}
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/crm_settings",
            headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=payload,
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("doctor snapshot persist failed: %s", exc)


def load_last_snapshot() -> dict[str, Any] | None:
    if not _configured():
        return None
    rows = _fetch(
        "crm_settings",
        {"key": f"eq.{SETTINGS_SNAPSHOT_KEY}", "select": "value,updated_at", "limit": "1"},
    )
    if not rows:
        return None
    raw = rows[0].get("value")
    if not raw:
        return None
    try:
        snap = json.loads(raw)
        snap["__persisted_at"] = rows[0].get("updated_at")
        return snap
    except Exception:
        return None


# ── Public entrypoint ────────────────────────────────────────────────────────


DIAGNOSERS: list[Callable[[], dict[str, Any]]] = [
    _diagnose_new_backlog,
    _diagnose_scanning_orphans,
    _diagnose_scanned_backlog,
    _diagnose_ready_backlog,
    _diagnose_apollo_credits,
    _diagnose_recent_zb_softdrops,
    _diagnose_no_active_mailboxes,
    _diagnose_mailbox_caps_exhausted,
    _diagnose_mailbox_high_bounce,
]


def run_pipeline_doctor(*, auto_fix: bool = True, sms_on_critical: bool = True) -> dict[str, Any]:
    """Diagnose every outbound-pipeline bucket and optionally auto-fix.

    Returns a structured snapshot suitable for the CEO dashboard, the
    ``ARIA, why is the pipeline stuck?`` AI command, and the CEO SMS
    escalation path. Also persisted to ``crm_settings`` so downstream
    surfaces can render the latest state without re-running every tick.
    """
    if not _configured():
        return {"ok": False, "reason": "supabase not configured"}

    snapshot = {
        "ok": True,
        "started_at": _iso(_now()),
        "buckets": [],
        "applied_fixes": {},
        "critical_buckets": [],
        "summary": "",
    }
    critical: list[str] = []
    total_stuck = 0

    for diag in DIAGNOSERS:
        try:
            result = diag()
        except Exception as exc:  # pragma: no cover — diagnose isolation
            logger.exception("doctor diagnose failed")
            result = {
                "bucket": diag.__name__,
                "stuck": 0,
                "severity": "info",
                "diagnosis": f"diagnose error: {exc}",
            }
        snapshot["buckets"].append(result)
        total_stuck += int(result.get("stuck") or 0)
        if result.get("severity") == "critical":
            critical.append(result["bucket"])

        # Autonomous escape hatch. Apply when there is *any* stuck work in a
        # bucket we know how to fix. Each fix is idempotent so a no-op stuck
        # count will just return `processed: 0`.
        if auto_fix and result.get("stuck") and result.get("bucket") in FIXES:
            try:
                fix_out = FIXES[result["bucket"]]()
            except Exception as exc:
                logger.exception("doctor fix %s failed", result["bucket"])
                fix_out = {"applied": False, "error": str(exc)[:400]}
            snapshot["applied_fixes"][result["bucket"]] = fix_out

    snapshot["critical_buckets"] = critical
    snapshot["total_stuck"] = total_stuck
    snapshot["finished_at"] = _iso(_now())

    parts = []
    for b in snapshot["buckets"]:
        if b.get("stuck"):
            parts.append(f"{b['bucket']}={b['stuck']}")
    snapshot["summary"] = (
        "Pipeline healthy — no stuck buckets." if not parts else "Stuck: " + ", ".join(parts)
    )

    _persist_snapshot(snapshot)

    if sms_on_critical and critical:
        try:
            from services.crm_openphone import send_ceo_sms

            lines = [
                f"ARIA Pipeline Doctor — {len(critical)} critical bucket(s):",
                *[
                    f"• {b['bucket']}: {b.get('stuck')} stuck — "
                    f"{(b.get('diagnosis') or '').strip()[:160]}"
                    for b in snapshot["buckets"]
                    if b.get("severity") == "critical"
                ],
                "Auto-fixes applied where safe. Check dashboard for details.",
            ]
            send_ceo_sms("\n".join(lines)[:1500])
        except Exception:
            logger.exception("doctor CEO SMS escalation failed")

    return snapshot
