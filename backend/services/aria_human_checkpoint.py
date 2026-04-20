"""Human-checkpoint classifier for the autonomous reply loop.

If a prospect's reply mentions legal review, a custom contract, a
multi-location deployment, or a monthly contract value at/above the
configured threshold (default $5k), we do NOT auto-send. The reply is
flagged ``status='needs_human'`` in ``aria_inbound_replies`` with a
``checkpoint_reason`` and the CEO + closer are SMS-alerted.

Pure string heuristics — deterministic, testable, cheap. We explicitly
avoid an LLM here because a false negative (auto-replying to an
enterprise lead) is much worse than a false positive (sending to the
VA queue for manual review).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import ARIA_HUMAN_CHECKPOINT_USD
from services import aria_settings


@dataclass(frozen=True)
class CheckpointDecision:
    trip: bool
    reason: str  # human-readable reason; empty when trip=False


_LEGAL_PATTERNS = [
    r"\blegal\b",
    r"\bour (?:counsel|lawyer|attorney|attorneys?)\b",
    r"\b(?:nda|msa|dpa|baa)\b",
    r"\bprivacy officer\b",
    r"\bindemni(?:ty|fication|fy)\b",
    r"\bliability cap\b",
    r"\bredlines?\b",
    r"\bcompliance review\b",
]

_CUSTOM_CONTRACT_PATTERNS = [
    r"\bcustom (?:contract|agreement|quote|proposal|pricing)\b",
    r"\benterprise (?:contract|agreement|quote|pricing|plan)\b",
    r"\bvendor (?:onboarding|security review|questionnaire)\b",
    r"\bmaster (?:services? )?agreement\b",
]

_SCALE_PATTERNS = [
    r"\b(?:[5-9]|[1-9]\d+)\s*(?:clinics?|offices?|locations?|branches?|sites?)\b",
    r"\bmulti[- ]?location\b",
    r"\bacross (?:[5-9]|[1-9]\d+)\s*(?:clinics?|offices?|locations?)\b",
]


def _money_above_threshold(text: str, threshold_usd: int) -> bool:
    """True if the text contains a dollar figure ≥ threshold interpreted as USD/CAD monthly."""
    # Handles "$5,000/month", "5k/mo", "USD 10,000 per month", "10,000 mo"
    matches = re.findall(
        r"\$?\s*([0-9]{1,3}(?:[,.][0-9]{3})+|[0-9]+(?:\.[0-9]+)?)\s*(k|thousand|million|m)?",
        text,
        flags=re.IGNORECASE,
    )
    for raw, suffix in matches:
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        mult = 1.0
        if suffix:
            s = suffix.lower()
            if s in ("k", "thousand"):
                mult = 1_000.0
            elif s in ("m", "million"):
                mult = 1_000_000.0
        amount = value * mult
        if amount >= threshold_usd:
            return True
    return False


def evaluate(reply_body: str, reply_subject: str | None = None) -> CheckpointDecision:
    """Return a checkpoint decision — ``trip=True`` blocks auto-send."""
    haystack = (reply_subject or "") + "\n" + (reply_body or "")
    haystack_lc = haystack.lower()

    for pattern in _LEGAL_PATTERNS:
        if re.search(pattern, haystack_lc):
            return CheckpointDecision(True, "legal review / privacy / liability language")
    for pattern in _CUSTOM_CONTRACT_PATTERNS:
        if re.search(pattern, haystack_lc):
            return CheckpointDecision(True, "custom-contract / MSA / enterprise language")
    for pattern in _SCALE_PATTERNS:
        if re.search(pattern, haystack_lc):
            return CheckpointDecision(True, "multi-location / enterprise scope")

    threshold = aria_settings.get_int(
        "aria_human_checkpoint_usd_threshold", ARIA_HUMAN_CHECKPOINT_USD
    )
    if _money_above_threshold(haystack, threshold):
        return CheckpointDecision(True, f"deal value ≥ ${threshold:,}/mo")

    return CheckpointDecision(False, "")


__all__ = ["evaluate", "CheckpointDecision"]
