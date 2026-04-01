"""
IBM Cost of a Data Breach — sector averages (USD, rounded) for narrative context.
Figures are approximate public-report baselines; refresh annually from IBM/Ponemon.
"""
from __future__ import annotations

# Average total cost (USD) — sector baselines; refresh annually from IBM/Ponemon
SECTOR_AVG_USD: dict[str, int] = {
    "global_avg": 4_880_000,
    "healthcare": 10_930_000,
    "financial": 9_440_000,
    "dental": 10_200_000,  # aligned with healthcare SMB exposure
    "medical": 10_930_000,
    "legal": 5_200_000,
    "professional_services": 5_200_000,
    "technology": 5_010_000,
    "retail": 3_860_000,
    "manufacturing": 4_730_000,
}


def resolve_sector_key(industry: str | None) -> str:
    if not industry:
        return "global_avg"
    t = industry.lower()
    if any(x in t for x in ("dental", "dentist", "orthodont")):
        return "dental"
    if any(x in t for x in ("health", "medical", "clinic", "hospital", "hipaa")):
        return "healthcare"
    if any(x in t for x in ("bank", "financial", "credit", "wealth", "investment")):
        return "financial"
    if any(x in t for x in ("legal", "law", "attorney")):
        return "legal"
    return "global_avg"


def build_estimate(industry: str | None, findings_count: int, critical_count: int) -> dict:
    """Report section payload for Supabase `breach_cost_estimate` and PDFs."""
    sector = resolve_sector_key(industry)
    baseline = SECTOR_AVG_USD.get(sector, SECTOR_AVG_USD["global_avg"])
    # Simple exposure tilt: many critical findings suggests higher incident likelihood (narrative only)
    risk_note = (
        f"Sector baseline (~${baseline:,.0f}) from IBM-style averages; "
        f"{critical_count} critical-class exposures increase likelihood of costly incidents."
        if critical_count
        else f"Sector baseline (~${baseline:,.0f}) from IBM-style averages; no critical-class items flagged in this pass."
    )
    return {
        "methodology": "IBM 2025 Cost of a Data Breach Report (sector averages, USD)",
        "sector_key": sector,
        "baseline_usd": baseline,
        "findings_count": findings_count,
        "critical_count": critical_count,
        "summary": risk_note,
    }
