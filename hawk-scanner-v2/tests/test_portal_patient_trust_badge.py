"""Unit tests for the Patient Trust Badge (priority list item #38).

The eligibility logic and SVG renderer are pure-Python so we pin the
contract from the test side without httpx / Supabase / FastAPI:

1. ``is_healthcare_vertical`` is a strict membership check against the
   curated list — substring matching is not allowed (e.g. a vertical
   like ``biomedical_supply`` must NOT earn a HIPAA-aligned badge).
2. ``patient_trust_eligibility`` returns a structured shape that the
   API + UI both rely on, with the right ``reason`` string for each
   denial path so the UI can show a useful explanation.
3. ``render_patient_trust_badge_svg`` escapes the company name so a
   stray ``<script>`` or ``&`` can never produce malformed XML.
4. ``embed_snippets`` HTML-escapes both URLs and the practice name in
   the alt text.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------- is_healthcare_vertical --------------------------------------


@pytest.mark.parametrize(
    "vertical",
    [
        "dental",
        "DENTAL",
        " dental ",
        "medical",
        "pharmacy",
        "mental_health",
        "optometry",
        "chiropractic",
        "physical_therapy",
    ],
)
def test_is_healthcare_vertical_accepts_curated_list(vertical: str) -> None:
    from services.portal_patient_trust_badge import is_healthcare_vertical

    assert is_healthcare_vertical(vertical) is True


@pytest.mark.parametrize(
    "vertical",
    [
        None,
        "",
        "legal",
        "accounting",
        "real_estate",
        # Substring traps — must NOT match.
        "biomedical_supply",
        "dental_supply_distributor",
        "medical_billing_software",
        "pharmacy_management_consulting",
    ],
)
def test_is_healthcare_vertical_rejects_non_healthcare(vertical: str | None) -> None:
    from services.portal_patient_trust_badge import is_healthcare_vertical

    assert is_healthcare_vertical(vertical) is False


# ---------- patient_trust_eligibility -----------------------------------


def _bundle(
    *,
    industry: str | None = "dental",
    certified_at: str | None = None,
    readiness_pct: int | None = None,
    cached_readiness: int | None = None,
) -> dict:
    """Build a minimal portal bundle matching ``load_portal_client_bundle``."""
    scan: dict = {}
    if readiness_pct is not None:
        scan = {"findings": {"insurance_readiness": {"readiness_pct": readiness_pct}}}
    return {
        "cpp": {"company_name": "Acme Dental"},
        "client": {
            "id": "client-1",
            "certified_at": certified_at,
            "hawk_readiness_score": cached_readiness,
        },
        "prospect": {"industry": industry},
        "scan": scan,
    }


def test_eligibility_certified_clinic() -> None:
    from services.portal_patient_trust_badge import patient_trust_eligibility

    out = patient_trust_eligibility(_bundle(certified_at="2026-01-01T00:00:00Z"))
    assert out["eligible"] is True
    assert out["reason"] == "hawk_certified"
    assert out["vertical"] == "dental"


def test_eligibility_above_floor() -> None:
    from services.portal_patient_trust_badge import patient_trust_eligibility

    out = patient_trust_eligibility(_bundle(readiness_pct=82))
    assert out["eligible"] is True
    assert out["reason"] == "insurance_readiness_above_floor"
    assert out["readiness_pct"] == 82


def test_eligibility_falls_back_to_cached_score_on_client() -> None:
    from services.portal_patient_trust_badge import patient_trust_eligibility

    out = patient_trust_eligibility(_bundle(cached_readiness=90))
    assert out["eligible"] is True
    assert out["readiness_pct"] == 90


def test_eligibility_below_floor_returns_specific_reason() -> None:
    from services.portal_patient_trust_badge import patient_trust_eligibility

    out = patient_trust_eligibility(_bundle(readiness_pct=72))
    assert out["eligible"] is False
    assert out["reason"] == "below_readiness_floor"


def test_eligibility_non_healthcare_short_circuits() -> None:
    """Even with high readiness + certified, non-health verticals are blocked."""
    from services.portal_patient_trust_badge import patient_trust_eligibility

    out = patient_trust_eligibility(
        _bundle(
            industry="legal",
            certified_at="2026-01-01T00:00:00Z",
            readiness_pct=95,
        )
    )
    assert out["eligible"] is False
    assert out["reason"] == "not_healthcare_vertical"


def test_eligibility_treats_zero_readiness_explicitly() -> None:
    """``readiness_pct: 0`` is a real value — not ``None`` — and should be
    reported back as ``0`` (so the UI can show the gap clearly), not
    silently dropped by truthy-coercion."""
    from services.portal_patient_trust_badge import patient_trust_eligibility

    out = patient_trust_eligibility(_bundle(readiness_pct=0))
    assert out["eligible"] is False
    assert out["reason"] == "below_readiness_floor"
    assert out["readiness_pct"] == 0


def test_eligibility_no_bundle_returns_no_profile_reason() -> None:
    from services.portal_patient_trust_badge import patient_trust_eligibility

    assert patient_trust_eligibility(None)["reason"] == "no_portal_profile"
    assert patient_trust_eligibility({})["reason"] == "not_healthcare_vertical"


# ---------- render_patient_trust_badge_svg ------------------------------


def test_render_includes_practice_name_and_date() -> None:
    from services.portal_patient_trust_badge import render_patient_trust_badge_svg

    svg = render_patient_trust_badge_svg(
        company_name="Acme Dental Care",
        earned_on="2026-01-12",
    )
    assert "<svg" in svg and "</svg>" in svg
    assert "Acme Dental Care" in svg
    assert "2026-01-12" in svg
    assert "PATIENT DATA PROTECTED" in svg
    assert "HIPAA-ALIGNED" in svg


def test_render_escapes_xml_dangerous_characters() -> None:
    """A stray ``<script>`` or ``&`` in a practice name must be HTML-escaped."""
    from services.portal_patient_trust_badge import render_patient_trust_badge_svg

    svg = render_patient_trust_badge_svg(
        company_name="<script>alert('x')</script> & friends",
        earned_on="<bad>",
    )
    # Raw tag must NOT survive into the SVG output.
    assert "<script>" not in svg
    # Escaped form must appear instead.
    assert "&lt;script&gt;" in svg
    # Ampersand in the body must be escaped to ``&amp;``.
    assert "&amp; friends" in svg


def test_render_handles_empty_inputs() -> None:
    from services.portal_patient_trust_badge import render_patient_trust_badge_svg

    svg = render_patient_trust_badge_svg(company_name="", earned_on=None)
    assert "<svg" in svg
    # Default placeholder kicks in.
    assert "Your practice" in svg


# ---------- embed_snippets ----------------------------------------------


def test_embed_snippets_escape_quotes_and_company() -> None:
    from services.portal_patient_trust_badge import embed_snippets

    out = embed_snippets(
        badge_url="https://example.com/badge.svg?id=1&x=2",
        verify_url="https://example.com/verify",
        company_name='Smith & Jones "Dentistry"',
    )
    # Both URL params and the alt text get HTML-escaped (``&`` → ``&amp;``,
    # ``"`` → ``&quot;``).
    assert "&amp;" in out["html"]
    assert "&quot;" in out["html"]
    assert "<script>" not in out["html"]
    # Plain copies of the URLs are preserved for the "copy URL" UI.
    assert out["image_url"] == "https://example.com/badge.svg?id=1&x=2"
    assert out["verify_url"] == "https://example.com/verify"
