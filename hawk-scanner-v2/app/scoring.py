"""Weighted scoring + industry multiplier (HAWK Scanner 2.0)."""
from __future__ import annotations

import re

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


def compute_score(findings: list[dict], industry: str | None = None) -> tuple[int, str, float]:
    """
    Start at 100; subtract weighted deductions times industry multiplier; clamp to 0–100.
    Returns (score, letter_grade, multiplier_used).
    """
    mult = industry_multiplier(industry)
    total_deduction = 0.0
    for f in findings:
        sev = normalize_severity(str(f.get("severity", "low")))
        base = float(SEVERITY_DEDUCTION.get(sev, 8))
        total_deduction += base * mult
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
