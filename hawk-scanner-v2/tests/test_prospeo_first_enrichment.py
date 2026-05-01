"""Tests for priority-list #17: Prospeo-first / Apollo-fallback enrichment.

Verifies:
1. ``generic_email_filter.is_generic_email`` correctly classifies role-based
   prefixes and passes named decision-maker emails.
2. ``aria_post_scan_pipeline._usable_enrichment`` rejects generic emails.
3. ``aria_post_scan_pipeline._enrich_single`` tries Prospeo first, falls back
   to Apollo, and rejects generic emails from both sources.
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, patch

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── generic_email_filter tests ───────────────────────────────────────────


def test_generic_prefixes_blocked() -> None:
    from services.generic_email_filter import is_generic_email

    for addr in (
        "info@example.com",
        "contact@clinic.com",
        "hello@lawfirm.com",
        "admin@cpa.com",
        "office@dental.com",
        "support@practice.com",
        "enquiries@example.com",
        "mail@example.com",
        "team@example.com",
        "HELLO@EXAMPLE.COM",
        "support+test@example.com",
    ):
        assert is_generic_email(addr), f"should be generic: {addr!r}"


def test_named_emails_pass() -> None:
    from services.generic_email_filter import is_generic_email

    for addr in (
        "jsmith@example.com",
        "dr.jones@clinic.com",
        "michael.lee@dental.com",
        "owner@example.com",
        "k.tan@lawfirm.com",
    ):
        assert not is_generic_email(addr), f"should NOT be generic: {addr!r}"


def test_edge_cases() -> None:
    from services.generic_email_filter import is_generic_email

    assert not is_generic_email("")
    assert not is_generic_email("noemail")
    assert not is_generic_email("@example.com")


# ── _usable_enrichment tests ────────────────────────────────────────────


def test_usable_enrichment_accepts_named_email() -> None:
    from services.aria_post_scan_pipeline import _usable_enrichment

    result = {"email": "dr.jones@clinic.com", "first_name": "Bob", "source": "prospeo"}
    assert _usable_enrichment(result) is result


def test_usable_enrichment_rejects_generic_email() -> None:
    from services.aria_post_scan_pipeline import _usable_enrichment

    result = {"email": "info@clinic.com", "first_name": "", "source": "prospeo"}
    assert _usable_enrichment(result) is None


def test_usable_enrichment_rejects_none() -> None:
    from services.aria_post_scan_pipeline import _usable_enrichment

    assert _usable_enrichment(None) is None


def test_usable_enrichment_rejects_empty_email() -> None:
    from services.aria_post_scan_pipeline import _usable_enrichment

    assert _usable_enrichment({"email": "", "source": "apollo"}) is None


# ── _enrich_single tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_single_prospeo_first() -> None:
    """Prospeo returns a good contact → Apollo should NOT be called."""
    from services.aria_post_scan_pipeline import _enrich_single

    prospeo_hit = {"email": "dr.jones@clinic.com", "first_name": "Bob", "last_name": "Jones", "source": "prospeo"}
    prospect = {"id": "p1", "domain": "clinic.com", "company_name": "Clinic"}

    with patch("services.aria_post_scan_pipeline._prospeo_enrich", new_callable=AsyncMock, return_value=prospeo_hit) as mock_p, \
         patch("services.aria_post_scan_pipeline._apollo_enrich", new_callable=AsyncMock) as mock_a:
        result = await _enrich_single(prospect, "dental")
        assert result is not None
        assert result["email"] == "dr.jones@clinic.com"
        assert result["source"] == "prospeo"
        mock_p.assert_awaited_once()
        mock_a.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_single_apollo_fallback() -> None:
    """Prospeo returns nothing → Apollo should be tried."""
    from services.aria_post_scan_pipeline import _enrich_single

    apollo_hit = {"email": "dr.smith@clinic.com", "first_name": "Jane", "last_name": "Smith", "source": "apollo"}
    prospect = {"id": "p2", "domain": "clinic.com", "company_name": "Clinic"}

    with patch("services.aria_post_scan_pipeline._prospeo_enrich", new_callable=AsyncMock, return_value=None), \
         patch("services.aria_post_scan_pipeline._apollo_enrich", new_callable=AsyncMock, return_value=apollo_hit):
        result = await _enrich_single(prospect, "dental")
        assert result is not None
        assert result["email"] == "dr.smith@clinic.com"
        assert result["source"] == "apollo"


@pytest.mark.asyncio
async def test_enrich_single_both_miss() -> None:
    """Both sources return nothing → result is None."""
    from services.aria_post_scan_pipeline import _enrich_single

    prospect = {"id": "p3", "domain": "clinic.com", "company_name": "Clinic"}

    with patch("services.aria_post_scan_pipeline._prospeo_enrich", new_callable=AsyncMock, return_value=None), \
         patch("services.aria_post_scan_pipeline._apollo_enrich", new_callable=AsyncMock, return_value=None):
        result = await _enrich_single(prospect, "dental")
        assert result is None


@pytest.mark.asyncio
async def test_enrich_single_generic_prospeo_falls_to_apollo() -> None:
    """Prospeo returns a generic email → treated as miss → Apollo tried."""
    from services.aria_post_scan_pipeline import _enrich_single

    generic_hit = {"email": "info@clinic.com", "first_name": "", "last_name": "", "source": "prospeo"}
    apollo_hit = {"email": "dr.smith@clinic.com", "first_name": "Jane", "last_name": "Smith", "source": "apollo"}
    prospect = {"id": "p4", "domain": "clinic.com", "company_name": "Clinic"}

    with patch("services.aria_post_scan_pipeline._prospeo_enrich", new_callable=AsyncMock, return_value=generic_hit), \
         patch("services.aria_post_scan_pipeline._apollo_enrich", new_callable=AsyncMock, return_value=apollo_hit):
        result = await _enrich_single(prospect, "dental")
        assert result is not None
        assert result["email"] == "dr.smith@clinic.com"


@pytest.mark.asyncio
async def test_enrich_single_generic_both_sources() -> None:
    """Both sources return generic emails → result is None."""
    from services.aria_post_scan_pipeline import _enrich_single

    generic1 = {"email": "info@clinic.com", "source": "prospeo"}
    generic2 = {"email": "contact@clinic.com", "source": "apollo"}
    prospect = {"id": "p5", "domain": "clinic.com", "company_name": "Clinic"}

    with patch("services.aria_post_scan_pipeline._prospeo_enrich", new_callable=AsyncMock, return_value=generic1), \
         patch("services.aria_post_scan_pipeline._apollo_enrich", new_callable=AsyncMock, return_value=generic2):
        result = await _enrich_single(prospect, "dental")
        assert result is None


@pytest.mark.asyncio
async def test_enrich_single_prospeo_error_falls_to_apollo() -> None:
    """Prospeo raises an exception → Apollo should still be tried."""
    from services.aria_post_scan_pipeline import _enrich_single

    apollo_hit = {"email": "dr.jones@clinic.com", "first_name": "Bob", "last_name": "Jones", "source": "apollo"}
    prospect = {"id": "p6", "domain": "clinic.com", "company_name": "Clinic"}

    with patch("services.aria_post_scan_pipeline._prospeo_enrich", new_callable=AsyncMock, side_effect=RuntimeError("API down")), \
         patch("services.aria_post_scan_pipeline._apollo_enrich", new_callable=AsyncMock, return_value=apollo_hit):
        result = await _enrich_single(prospect, "dental")
        assert result is not None
        assert result["email"] == "dr.jones@clinic.com"


@pytest.mark.asyncio
async def test_enrich_single_empty_domain() -> None:
    """Empty domain → immediate None, no API calls."""
    from services.aria_post_scan_pipeline import _enrich_single

    prospect = {"id": "p7", "domain": "", "company_name": "Clinic"}

    with patch("services.aria_post_scan_pipeline._prospeo_enrich", new_callable=AsyncMock) as mock_p, \
         patch("services.aria_post_scan_pipeline._apollo_enrich", new_callable=AsyncMock) as mock_a:
        result = await _enrich_single(prospect, "dental")
        assert result is None
        mock_p.assert_not_awaited()
        mock_a.assert_not_awaited()
