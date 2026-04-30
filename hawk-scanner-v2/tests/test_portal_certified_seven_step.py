"""Unit tests for the HAWK Certified 7-step tracker (priority list #35).

Covers:

1. The detection helpers (``is_dmarc_strict``, ``is_spf_strict``,
   ``is_insurance_readiness_above_80``) against realistic finding rows
   matching what the email_security analyzer + insurance_readiness pipe
   produce, plus negative cases.
2. ``hawk_certified_progress`` projects a list of milestone rows into
   the 7-step structure with correct ``done`` / ``achieved_at`` values.
3. ``_render_certified_badge_svg`` produces well-formed SVG with the
   company name + cert date HTML-escaped (no XSS via SVG ``<text>``).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------- detection helpers ----------------------------------------------


@pytest.fixture
def dmarc_finding_strict() -> dict:
    return {
        "title": "DMARC policy",
        "severity": "ok",
        "description": "DMARC policy is reject — strong.",
        "technical_detail": "v=DMARC1; p=reject; rua=mailto:dmarc@example.com",
    }


@pytest.fixture
def dmarc_finding_quarantine() -> dict:
    return {
        "title": "DMARC policy",
        "severity": "low",
        "description": "DMARC policy is quarantine — good; consider reject when stable.",
        "technical_detail": "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com",
    }


@pytest.fixture
def dmarc_finding_none() -> dict:
    return {
        "title": "DMARC policy",
        "severity": "medium",
        "description": "DMARC p=none — monitoring only; increase to quarantine/reject.",
        "technical_detail": "v=DMARC1; p=none; rua=mailto:dmarc@example.com",
    }


def _scan_with(findings: list[dict]) -> dict:
    return {"id": "scan-1", "findings": {"findings": findings}}


def test_is_dmarc_strict_accepts_reject(dmarc_finding_strict: dict) -> None:
    from services.portal_milestones import is_dmarc_strict

    assert is_dmarc_strict(_scan_with([dmarc_finding_strict])) is True


def test_is_dmarc_strict_accepts_quarantine(dmarc_finding_quarantine: dict) -> None:
    from services.portal_milestones import is_dmarc_strict

    assert is_dmarc_strict(_scan_with([dmarc_finding_quarantine])) is True


def test_is_dmarc_strict_rejects_p_none(dmarc_finding_none: dict) -> None:
    from services.portal_milestones import is_dmarc_strict

    assert is_dmarc_strict(_scan_with([dmarc_finding_none])) is False


def test_is_dmarc_strict_returns_false_when_finding_absent() -> None:
    from services.portal_milestones import is_dmarc_strict

    assert is_dmarc_strict(_scan_with([])) is False


def test_is_spf_strict_accepts_dash_all() -> None:
    from services.portal_milestones import is_spf_strict

    finding = {
        "title": "SPF policy",
        "severity": "ok",
        "description": "SPF uses strict fail (-all) — good.",
        "technical_detail": "v=spf1 include:_spf.google.com -all",
    }
    assert is_spf_strict(_scan_with([finding])) is True


def test_is_spf_strict_rejects_tilde_all() -> None:
    from services.portal_milestones import is_spf_strict

    finding = {
        "title": "SPF policy",
        "severity": "low",
        "description": "SPF uses softfail (~all) — acceptable.",
        "technical_detail": "v=spf1 include:_spf.google.com ~all",
    }
    assert is_spf_strict(_scan_with([finding])) is False


def test_is_insurance_readiness_above_80_dict_form() -> None:
    from services.portal_milestones import is_insurance_readiness_above_80

    scan = {"findings": {"insurance_readiness": {"score": 82}, "findings": []}}
    assert is_insurance_readiness_above_80(scan) is True


def test_is_insurance_readiness_above_80_int_form() -> None:
    from services.portal_milestones import is_insurance_readiness_above_80

    scan = {"findings": {"insurance_readiness": 80, "findings": []}}
    assert is_insurance_readiness_above_80(scan) is True


def test_is_insurance_readiness_below_80_returns_false() -> None:
    from services.portal_milestones import is_insurance_readiness_above_80

    scan = {"findings": {"insurance_readiness": {"score": 79}, "findings": []}}
    assert is_insurance_readiness_above_80(scan) is False


def test_is_insurance_readiness_above_80_missing_returns_false() -> None:
    from services.portal_milestones import is_insurance_readiness_above_80

    assert is_insurance_readiness_above_80({"findings": {"findings": []}}) is False


# ---------- hawk_certified_progress ----------------------------------------


def test_hawk_certified_progress_empty_input() -> None:
    from services.portal_milestones import hawk_certified_progress

    out = hawk_certified_progress([])
    assert out["completed"] == 0
    assert out["total"] == 7
    assert len(out["steps"]) == 7
    assert all(s["done"] is False for s in out["steps"])
    assert all(s["achieved_at"] is None for s in out["steps"])


def test_hawk_certified_progress_marks_done_with_timestamp() -> None:
    from services.portal_milestones import hawk_certified_progress

    rows = [
        {"milestone_key": "spf_strict", "achieved_at": "2026-01-15T12:00:00Z"},
        {"milestone_key": "dmarc_strict", "achieved_at": "2026-01-15T12:01:00Z"},
        {"milestone_key": "score_above_70", "achieved_at": "2026-02-01T09:00:00Z"},
    ]
    out = hawk_certified_progress(rows, certified_at=None)
    assert out["completed"] == 3
    assert out["total"] == 7
    assert out["certified_at"] is None
    by_key = {s["key"]: s for s in out["steps"]}
    assert by_key["spf_strict"]["done"] is True
    assert by_key["spf_strict"]["achieved_at"] == "2026-01-15T12:00:00Z"
    assert by_key["thirty_days_clean"]["done"] is False


def test_hawk_certified_progress_handles_none_input() -> None:
    from services.portal_milestones import hawk_certified_progress

    out = hawk_certified_progress(None, certified_at="2026-03-01T00:00:00Z")
    assert out["completed"] == 0
    assert out["certified_at"] == "2026-03-01T00:00:00Z"


def test_hawk_certified_progress_step_order_is_stable() -> None:
    from services.portal_milestones import HAWK_CERTIFIED_STEPS, hawk_certified_progress

    out = hawk_certified_progress([])
    keys = [s["key"] for s in out["steps"]]
    assert keys == [s["key"] for s in HAWK_CERTIFIED_STEPS]


# ---------- badge SVG ------------------------------------------------------


def test_badge_svg_contains_company_and_date() -> None:
    from routers.portal_phase2 import _render_certified_badge_svg

    svg = _render_certified_badge_svg("Acme Dental", "2026-04-15")
    assert svg.startswith('<?xml version="1.0"')
    assert "<svg" in svg
    assert "Acme Dental" in svg
    assert "2026-04-15" in svg
    assert "CERTIFIED" in svg


def test_badge_svg_escapes_html_in_company_name() -> None:
    from routers.portal_phase2 import _render_certified_badge_svg

    svg = _render_certified_badge_svg('Evil & "Co" <script>', "2026-04-15")
    assert "<script>" not in svg
    assert "&amp;" in svg
    assert "&quot;" in svg or "&#x27;" in svg or "&#34;" in svg
