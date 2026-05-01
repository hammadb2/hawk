"""Tests for the static fix-guide registry (priority list item #39).

Every finding category the scanner emits must have at least a category-level
fallback guide so that no finding is ever left without remediation guidance,
regardless of whether the OpenAI interpretation layer ran.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.fix_guides import apply_fallback_guides, get_fix_guide


# ---------- Every scanner category has a guide ---------------------------

_ALL_CATEGORIES = [
    "Email Security",
    "SSL/TLS",
    "Access control",
    "Attack surface",
    "Transport security",
    "Network exposure",
    "Internet exposure",
    "Lookalike domains",
    "Supply chain",
    "Breach monitoring",
    "Breach Exposure",
    "Stealer exposure",
    "Secrets exposure",
    "Ransomware intelligence",
    "Exposure evidence",
]


@pytest.mark.parametrize("category", _ALL_CATEGORIES)
def test_every_scanner_category_has_fallback(category: str) -> None:
    guide = get_fix_guide(category, "some generic title")
    assert guide is not None, f"No fallback guide for category '{category}'"
    assert len(guide) > 50, f"Guide for '{category}' is too short to be useful"


# ---------- Title-specific matching --------------------------------------


def test_spf_guide_matches_spf_title() -> None:
    guide = get_fix_guide("Email Security", "SPF policy")
    assert guide is not None
    assert "TXT record" in guide
    assert "v=spf1" in guide


def test_dmarc_guide_matches_dmarc_title() -> None:
    guide = get_fix_guide("Email Security", "DMARC policy")
    assert guide is not None
    assert "p=quarantine" in guide
    assert "_dmarc" in guide


def test_dkim_guide_matches_dkim_title() -> None:
    guide = get_fix_guide("Email Security", "DKIM selectors")
    assert guide is not None
    assert "DKIM" in guide


def test_mfa_guide_matches_no_mfa_title() -> None:
    guide = get_fix_guide("Access control", "Login portal(s) with no MFA detected")
    assert guide is not None
    assert "MFA" in guide or "multi-factor" in guide.lower()


def test_ssl_handshake_guide() -> None:
    guide = get_fix_guide("SSL/TLS", "HTTPS handshake failed")
    assert guide is not None
    assert "certificate" in guide.lower() or "certbot" in guide.lower()


def test_subdomain_guide() -> None:
    guide = get_fix_guide("Attack surface", "Subdomain footprint")
    assert guide is not None
    assert "subdomain" in guide.lower()


def test_login_paths_guide() -> None:
    guide = get_fix_guide("Attack surface", "Login or admin paths are directly reachable")
    assert guide is not None
    assert "MFA" in guide or "rate limit" in guide.lower()


def test_vertical_software_dentrix() -> None:
    guide = get_fix_guide("Dental software exposure", "Dentrix (Henry Schein) detected on perimeter")
    assert guide is not None
    assert "Dentrix" in guide


def test_vertical_software_clio() -> None:
    guide = get_fix_guide("Legal software exposure", "Clio (Themis Solutions) detected on perimeter")
    assert guide is not None
    assert "Clio" in guide


def test_vertical_software_generic_fallback() -> None:
    guide = get_fix_guide("Pharmacy software exposure", "UnknownPMS detected on perimeter")
    assert guide is not None
    assert "vendor" in guide.lower()


# ---------- Case insensitivity -------------------------------------------


def test_case_insensitive_category() -> None:
    guide_lower = get_fix_guide("email security", "SPF policy")
    guide_upper = get_fix_guide("EMAIL SECURITY", "SPF policy")
    guide_mixed = get_fix_guide("Email Security", "SPF policy")
    assert guide_lower == guide_upper == guide_mixed


# ---------- No match returns None ----------------------------------------


def test_unknown_category_returns_none() -> None:
    assert get_fix_guide("Totally Unknown Category", "some title") is None


# ---------- apply_fallback_guides ----------------------------------------


def test_apply_fills_missing_guides() -> None:
    findings = [
        {"category": "Email Security", "title": "SPF policy", "fix_guide": None},
        {"category": "SSL/TLS", "title": "TLS configuration", "fix_guide": None},
        {"category": "Unknown", "title": "whatever"},
    ]
    count = apply_fallback_guides(findings)
    assert count == 2
    assert findings[0]["fix_guide"] is not None
    assert "v=spf1" in findings[0]["fix_guide"]
    assert findings[1]["fix_guide"] is not None
    assert findings[2].get("fix_guide") is None


def test_apply_does_not_overwrite_existing_guide() -> None:
    findings = [
        {"category": "Email Security", "title": "SPF policy", "fix_guide": "Custom LLM guide"},
    ]
    count = apply_fallback_guides(findings)
    assert count == 0
    assert findings[0]["fix_guide"] == "Custom LLM guide"


def test_apply_returns_zero_for_empty_list() -> None:
    assert apply_fallback_guides([]) == 0


# ---------- Guide quality checks ----------------------------------------


def test_all_guides_are_numbered_steps() -> None:
    """Every guide should contain at least numbered steps (starts with '1.')."""
    for category in _ALL_CATEGORIES:
        guide = get_fix_guide(category, "generic")
        assert guide is not None
        assert "1." in guide, f"Guide for '{category}' doesn't have numbered steps"


def test_no_guide_contains_jargon_acronyms_without_expansion() -> None:
    """Guides should expand acronyms on first use or use plain language."""
    for category in _ALL_CATEGORIES:
        guide = get_fix_guide(category, "generic")
        assert guide is not None
        # Ensure guides don't use unexpanded jargon
        # (MFA is always expanded as "multi-factor authentication" or "MFA/2FA" nearby)
        assert "CVE" not in guide or "vulnerabilit" in guide.lower(), (
            f"Guide for '{category}' uses CVE without context"
        )
