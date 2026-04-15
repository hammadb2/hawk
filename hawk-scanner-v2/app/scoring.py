"""Weighted scoring + industry multiplier (HAWK Scanner 2.0)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.settings import Settings

# Per-finding deductions (applied before industry multiplier)
SEVERITY_DEDUCTION = {
    "critical": 25,
    "high": 15,
    "medium": 8,
    "low": 3,
    # legacy / tool mappings
    "warning": 8,
    "info": 3,
    "ok": 0,
}

_SENSITIVE_INDUSTRY = re.compile(
    r"dental|dentist|orthodont|medical|health|clinic|hospital|pharma|hipaa|"
    r"legal|law\s*firm|attorney|financial|finance|bank|credit\s*union|wealth|"
    r"accounting|cpa|investment",
    re.I,
)


def industry_multiplier(industry: str | None) -> float:
    if not industry:
        return 1.0
    return 1.3 if _SENSITIVE_INDUSTRY.search(industry.strip()) else 1.0


def normalize_severity(raw: str) -> str:
    s = (raw or "").lower().strip()
    if s == "warning":
        return "medium"
    if s in ("info", "informational", "information"):
        return "low"
    if s in ("critical", "high", "medium", "low", "ok"):
        return s
    if s in ("severe", "crit"):
        return "high"
    if s in ("warn",):
        return "medium"
    return "medium"


def _normalize_trust_level(raw: str | None) -> str:
    t = (raw or "public").strip().lower()
    if t in ("subscriber", "certified"):
        return t
    return "public"


def compute_score(
    findings: list[dict],
    industry: str | None = None,
    *,
    trust_level: str = "public",
    settings: "Settings | None" = None,
) -> tuple[int, str, float]:
    """
    Start at 100; subtract weighted deductions times industry multiplier; clamp to 0–100.

    trust_level:
      - public: minimum deduction floor (strict) so clean external passes rarely show A/B.
      - subscriber: softer floor for paid customers scanning a domain on their account.
      - certified: no floor — raw deductions only (remediation attested via HAWK API).
    """
    from app.settings import get_settings

    s = settings or get_settings()
    tl = _normalize_trust_level(trust_level)
    mult = industry_multiplier(industry)
    total_deduction = 0.0
    for f in findings:
        sev = normalize_severity(str(f.get("severity", "low")))
        base = float(SEVERITY_DEDUCTION.get(sev, 8))
        total_deduction += base * mult

    if tl == "certified":
        floor_pts = 0.0
    elif tl == "subscriber":
        floor_pts = float(s.strict_score_floor_subscriber) * mult
    else:
        floor_pts = float(s.strict_score_floor_public) * mult
    total_deduction = max(total_deduction, floor_pts)

    score = int(round(max(0.0, min(100.0, 100.0 - total_deduction))))

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"
    return score, grade, mult
