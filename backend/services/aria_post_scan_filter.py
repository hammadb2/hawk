"""Post-scan PASS / ARCHIVE / PRIORITY filter (priority list #15).

Sits between :mod:`services.aria_sla_auto_scan` (which writes the scan row)
and :mod:`services.aria_post_scan_pipeline` (which enriches + drafts a
Charlotte email). Keeps Charlotte focused on the leads that actually look
worth a sales motion and shunts the rest to ``pipeline_status='archived'``
without burning Apollo / OpenAI credits.

Decision rules (verbatim from the priority list):

PASS to Charlotte iff
    score < 80 AND has at least one HIGH or CRITICAL finding AND
    grade in {C, D, F}.

ARCHIVE iff
    score >= 80 OR only LOW/INFO findings OR grade in {A, B}.

PRIORITY FLAG (orthogonal to PASS/ARCHIVE — fire-and-forget signal):
    score < 50 OR has CRITICAL OR has breach record OR
    insurance readiness < 50% OR grade in {D, F}.

The two condition sets aren't strictly disjoint; ARCHIVE wins ties because
the spec says ARCHIVE on any of its conditions, and PASS only when all of
its conditions hold. So we evaluate ARCHIVE first and fall through to PASS
when none of the ARCHIVE conditions match.

Hourly counters are kept in a module-level :class:`HourlyCounters` so a
single-process Railway worker can self-report without a DB round-trip.
When the hour bucket rolls over the previous bucket is logged at INFO
with a structured prefix (``post_scan_hourly``) for log-aggregation rules.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

Decision = Literal["pass", "archive"]

# ── Severity buckets ─────────────────────────────────────────────────────

_HIGH_OR_CRITICAL = {"high", "critical"}
_LOW_OR_INFO = {"low", "info", "informational", "ok", "warning", "warn"}


def _findings_list(payload: Any) -> list[dict[str, Any]]:
    """Pull the findings list out of the scan row's ``findings`` blob.

    ``crm_prospect_scans.findings`` is either a bare list or
    ``{"findings": [...], ...}``. Anything else returns an empty list.
    """
    if isinstance(payload, list):
        return [f for f in payload if isinstance(f, dict)]
    if isinstance(payload, dict):
        inner = payload.get("findings")
        if isinstance(inner, list):
            return [f for f in inner if isinstance(f, dict)]
    return []


def _severities(findings: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for f in findings:
        s = str(f.get("severity") or "").strip().lower()
        if s:
            out.append(s)
    return out


def _has_breach_signal(scan_row: dict[str, Any], findings: list[dict[str, Any]]) -> bool:
    """True if any signal in the scan suggests a breach / credential exposure."""
    # Breach indicators bubble up through the breach_cost_estimate dict and
    # through individual findings tagged with breach / pwned / stealer
    # categories. Check both.
    bc = scan_row.get("breach_cost_estimate") or {}
    if isinstance(bc, dict):
        if bc.get("has_breach") or bc.get("breach_count"):
            return True
    for f in findings:
        cat = str(f.get("category") or "").lower()
        title = str(f.get("title") or "").lower()
        layer = str(f.get("layer") or "").lower()
        blob = f"{cat} {title} {layer}"
        if any(k in blob for k in ("breach", "pwned", "stealer", "credential leak", "infostealer")):
            return True
    return False


def _insurance_readiness_pct(scan_row: dict[str, Any]) -> int | None:
    """Return the integer readiness percentage if present.

    ``compute_insurance_readiness`` (in hawk-scanner-v2) emits
    ``{"readiness_pct": int, ...}``. We stash that inside the ``findings``
    JSON blob via :mod:`services.aria_sla_auto_scan` so this filter can
    read it without a schema migration.
    """
    findings = scan_row.get("findings")
    if isinstance(findings, dict):
        ins = findings.get("insurance_readiness")
        if isinstance(ins, dict):
            pct = ins.get("readiness_pct")
            if isinstance(pct, int):
                return pct
            try:
                return int(pct) if pct is not None else None
            except (TypeError, ValueError):
                return None
    # Fallback: some older scan rows had it on raw_layers.
    raw = scan_row.get("raw_layers")
    if isinstance(raw, dict):
        ins = raw.get("insurance_readiness")
        if isinstance(ins, dict):
            pct = ins.get("readiness_pct")
            if isinstance(pct, int):
                return pct
    return None


def _coerce_score(score: Any) -> int | None:
    if score is None:
        return None
    try:
        return int(score)
    except (TypeError, ValueError):
        return None


# ── Filter result ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FilterDecision:
    decision: Decision
    priority: bool
    reason: str
    # Diagnostics — useful for logs / debugging without re-deriving them.
    score: int | None
    grade: str
    has_critical: bool
    has_high_or_critical: bool
    only_low_or_info: bool
    has_breach: bool
    insurance_readiness_pct: int | None


def evaluate(scan_row: dict[str, Any]) -> FilterDecision:
    """Evaluate the PASS / ARCHIVE / PRIORITY rules on a scan row."""
    score = _coerce_score(scan_row.get("hawk_score"))
    grade = str(scan_row.get("grade") or "").strip().upper()

    findings = _findings_list(scan_row.get("findings"))
    sevs = _severities(findings)
    has_critical = "critical" in sevs
    has_high_or_critical = any(s in _HIGH_OR_CRITICAL for s in sevs)
    only_low_or_info = bool(sevs) and all(s in _LOW_OR_INFO for s in sevs)
    has_breach = _has_breach_signal(scan_row, findings)
    ins_pct = _insurance_readiness_pct(scan_row)

    # ARCHIVE wins ties — any of the ARCHIVE conditions short-circuits PASS.
    archive_reasons: list[str] = []
    if score is not None and score >= 80:
        archive_reasons.append(f"score>=80({score})")
    if only_low_or_info:
        archive_reasons.append("only_low_or_info_findings")
    if grade in {"A", "B"}:
        archive_reasons.append(f"grade={grade}")

    if archive_reasons:
        decision: Decision = "archive"
        reason = "archive: " + ",".join(archive_reasons)
    elif (
        score is not None
        and score < 80
        and has_high_or_critical
        and grade in {"C", "D", "F"}
    ):
        decision = "pass"
        reason = f"pass: score={score},grade={grade},has_high_or_critical=true"
    else:
        # Borderline: doesn't meet PASS gate, doesn't meet ARCHIVE gate.
        # The spec is strict — without HIGH/CRITICAL findings AND a poor
        # grade AND a sub-80 score, this lead isn't a Charlotte fit. Archive
        # it so we don't burn an Apollo lookup. Flag the reason so any
        # disagreement can be audited.
        decision = "archive"
        reason = (
            "archive: did_not_meet_pass_gate "
            f"score={score},grade={grade!r},has_high_or_critical={has_high_or_critical}"
        )

    priority = (
        (score is not None and score < 50)
        or has_critical
        or has_breach
        or (ins_pct is not None and ins_pct < 50)
        or grade in {"D", "F"}
    )

    return FilterDecision(
        decision=decision,
        priority=priority,
        reason=reason,
        score=score,
        grade=grade,
        has_critical=has_critical,
        has_high_or_critical=has_high_or_critical,
        only_low_or_info=only_low_or_info,
        has_breach=has_breach,
        insurance_readiness_pct=ins_pct,
    )


# ── Hourly counters ──────────────────────────────────────────────────────


class HourlyCounters:
    """Thread-safe per-hour-bucket counters with auto-flush on rollover.

    Single-process; the SLA scanner runs inside the FastAPI app so there's
    only one of these instances per host. Multi-host deployments will get
    one log line per host per hour, which is exactly what we want for
    fan-out visibility.
    """

    _KEYS = ("scanned", "passed", "archived", "priority_flagged")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bucket = self._current_bucket()
        self._counts: dict[str, int] = {k: 0 for k in self._KEYS}

    @staticmethod
    def _current_bucket() -> str:
        # Truncate to the hour in UTC. ISO so log-aggregation can sort.
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")

    def record(self, *, decision: Decision, priority: bool) -> None:
        with self._lock:
            self._maybe_flush_locked()
            self._counts["scanned"] += 1
            if decision == "pass":
                self._counts["passed"] += 1
            else:
                self._counts["archived"] += 1
            if priority:
                self._counts["priority_flagged"] += 1

    def snapshot(self) -> tuple[str, dict[str, int]]:
        with self._lock:
            return self._bucket, dict(self._counts)

    def _maybe_flush_locked(self) -> None:
        now_bucket = self._current_bucket()
        if now_bucket == self._bucket:
            return
        # Bucket rolled over — emit the previous bucket's totals as a single
        # structured INFO line. Fields are flat keys (not nested JSON) so a
        # naive Sentry / Datadog grok pattern can split them.
        snapshot = dict(self._counts)
        logger.info(
            "post_scan_hourly bucket=%s scanned=%d passed=%d archived=%d priority_flagged=%d",
            self._bucket,
            snapshot["scanned"],
            snapshot["passed"],
            snapshot["archived"],
            snapshot["priority_flagged"],
        )
        self._bucket = now_bucket
        self._counts = {k: 0 for k in self._KEYS}


_counters = HourlyCounters()


def record_decision(decision: FilterDecision) -> None:
    _counters.record(decision=decision.decision, priority=decision.priority)


def current_counters() -> tuple[str, dict[str, int]]:
    """Used by tests / health endpoints. Returns (bucket, counts)."""
    return _counters.snapshot()
