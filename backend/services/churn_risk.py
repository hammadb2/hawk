"""
Churn risk score calculator for HAWK CRM.
Computes a 0–100 numeric score from health signals and maps it to a label.
Called on every sync and on critical events.

Score thresholds:
  0–39   = low
  40–59  = medium
  60–79  = high
  80+    = critical  → triggers immediate WhatsApp to rep + HoS
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


LABEL_LOW = "low"
LABEL_MEDIUM = "medium"
LABEL_HIGH = "high"
LABEL_CRITICAL = "critical"

THRESHOLD_HIGH = 60
THRESHOLD_CRITICAL = 80


@dataclass
class HealthSignals:
    """Input signals for churn risk calculation."""
    last_login_date: Optional[datetime] = None
    scans_this_month: int = 0
    onboarding_pct: int = 100
    nps_score: Optional[int] = None
    tickets_open_over_48h: int = 0
    payment_failed_count: int = 0
    cancellation_intent: bool = False
    downgrade_requested: bool = False
    reports_downloaded: bool = False
    sessions_this_month: int = 0

    # Positive signal bonuses
    extra_context: dict = field(default_factory=dict)


@dataclass
class ChurnRiskResult:
    numeric: int
    label: str
    signals_fired: list[str]
    is_critical: bool


def calculate(signals: HealthSignals) -> ChurnRiskResult:
    """
    Compute churn risk score from signals.
    Returns numeric score (0–100), label, and list of triggered signals.
    """
    score = 0
    fired: list[str] = []

    # ── Negative signals (add to score) ─────────────────────────────
    if signals.last_login_date is not None:
        days_no_login = (datetime.now(timezone.utc) - signals.last_login_date).days
        if days_no_login >= 14:
            score += 25
            fired.append(f"no_login_14d ({days_no_login}d)")
        elif days_no_login >= 7:
            score += 10
            fired.append(f"no_login_7d ({days_no_login}d)")
    else:
        # Never logged in
        score += 25
        fired.append("never_logged_in")

    if signals.scans_this_month == 0:
        score += 20
        fired.append("zero_scans_this_month")

    if signals.onboarding_pct < 50:
        score += 15
        fired.append(f"onboarding_under_50pct ({signals.onboarding_pct}%)")

    if signals.nps_score is not None and signals.nps_score <= 6:
        score += 20
        fired.append(f"nps_low ({signals.nps_score})")

    if signals.tickets_open_over_48h > 0:
        score += 10
        fired.append(f"open_ticket_48h ({signals.tickets_open_over_48h})")

    if signals.payment_failed_count >= 2:
        score += 30
        fired.append(f"payment_failed_2x ({signals.payment_failed_count})")
    elif signals.payment_failed_count == 1:
        score += 15
        fired.append("payment_failed_1x")

    if signals.cancellation_intent:
        score += 40
        fired.append("cancellation_intent")

    if signals.downgrade_requested:
        score += 35
        fired.append("downgrade_requested")

    # ── Positive signals (subtract from score) ───────────────────────
    if signals.scans_this_month >= 10:
        score -= 15
        fired.append(f"active_scanner ({signals.scans_this_month} scans)")

    if signals.reports_downloaded:
        score -= 10
        fired.append("reports_downloaded")

    if signals.nps_score is not None and signals.nps_score >= 9:
        score -= 20
        fired.append(f"nps_promoter ({signals.nps_score})")

    # Clamp to 0–100
    score = max(0, min(100, score))

    label = _score_to_label(score)

    return ChurnRiskResult(
        numeric=score,
        label=label,
        signals_fired=fired,
        is_critical=score >= THRESHOLD_CRITICAL,
    )


def _score_to_label(score: int) -> str:
    if score >= THRESHOLD_CRITICAL:
        return LABEL_CRITICAL
    if score >= THRESHOLD_HIGH:
        return LABEL_HIGH
    if score >= 40:
        return LABEL_MEDIUM
    return LABEL_LOW
