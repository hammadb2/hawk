"""Unit tests for the generic-email-prefix filter (priority list #17 audit fix).

Cold outreach to ``info@`` / ``contact@`` / ``support@`` style mailboxes burns
sender-domain reputation and tanks reply rates. These tests pin the policy:

1. ``_is_generic_email`` correctly classifies role-based prefixes (with and
   without ``+plus`` aliases, case-insensitive).
2. ``_map_gmaps_result`` drops generic prefixes from
   ``emails_from_website`` at extraction time so they never beat Prospeo +
   Apollo decision-maker contacts in ``_merge_emails``.
3. ``_merge_emails`` defensively re-filters generic emails on the way out
   (belt-and-suspenders against any future producer that bypasses the
   extraction-time filter).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_generic_email_prefixes_classified() -> None:
    from services.aria_apify_scraper import _is_generic_email

    for addr in (
        "info@dental.example",
        "contact@dental.example",
        "Hello@DENTAL.EXAMPLE",   # case-insensitive
        "support+test@dental.example",  # plus-alias stripped
        "  noreply@dental.example  ",
        "frontdesk@dental.example",
        "appointments@dental.example",
    ):
        assert _is_generic_email(addr), f"expected generic: {addr!r}"


def test_named_emails_not_classified_generic() -> None:
    from services.aria_apify_scraper import _is_generic_email

    for addr in (
        "jsmith@dental.example",
        "drrodriguez@dental.example",
        "michael.lee@dental.example",
        "k.tan@dental.example",
        "owner@dental.example",  # specific role; we do cold-outreach owners
    ):
        assert not _is_generic_email(addr), f"unexpectedly classified generic: {addr!r}"


def test_map_gmaps_result_drops_generic_emails() -> None:
    from services.aria_apify_scraper import _map_gmaps_result

    item = {
        "title": "Smile Dental",
        "website": "https://smile-dental.example",
        "address": "1 Main St, Boston, MA",
        "city": "Boston",
        "state": "MA",
        "phone": "+1-555-0100",
        "totalScore": 4.7,
        "reviewsCount": 120,
        # Mix of generic + named emails — only the named one should survive.
        "emails": ["info@smile-dental.example", "drsmith@smile-dental.example"],
        "contactEmail": "contact@smile-dental.example",
    }
    out = _map_gmaps_result(item, vertical="dental", city="Boston")
    assert out is not None
    assert out["emails_from_website"] == ["drsmith@smile-dental.example"]


def test_map_gmaps_result_returns_empty_when_only_generic() -> None:
    from services.aria_apify_scraper import _map_gmaps_result

    item = {
        "title": "Generic Practice",
        "website": "https://generic-practice.example",
        "address": "2 Oak Ave, Boston, MA",
        "city": "Boston",
        "state": "MA",
        "phone": "+1-555-0101",
        "emails": ["info@generic-practice.example"],
        "contactEmail": "contact@generic-practice.example",
    }
    out = _map_gmaps_result(item, vertical="dental", city="Boston")
    assert out is not None
    # No usable email — lead should fall through to Prospeo / Apollo / suppressed.
    assert out["emails_from_website"] == []


def test_merge_emails_skips_generic_actor1_falls_through_to_apollo() -> None:
    """Defensive belt-and-suspenders: even if a generic email leaks into
    ``actor1_emails``, ``_merge_emails`` must skip it and use the Apollo
    decision-maker contact instead."""
    from services.aria_apify_scraper import _merge_emails

    leads = [
        {"domain": "smile-dental.example", "business_name": "Smile Dental"},
    ]
    actor1 = {"smile-dental.example": ["info@smile-dental.example"]}
    apollo = {
        "smile-dental.example": {
            "email": "drsmith@smile-dental.example",
            "first_name": "Jane",
            "last_name": "Smith",
            "title": "Owner",
            "source": "apollo",
        }
    }
    with_email, without_email = _merge_emails(leads, actor1, apollo)
    assert len(with_email) == 1
    assert without_email == []
    assert with_email[0]["contact_email"] == "drsmith@smile-dental.example"
    assert with_email[0]["email_finder"] == "apollo"


def test_merge_emails_suppresses_when_only_generic_and_no_fallback() -> None:
    """If actor1 only has a generic email and Apollo has nothing, the lead
    must be suppressed — we never cold-email an unaddressed mailbox."""
    from services.aria_apify_scraper import _merge_emails

    leads = [
        {"domain": "generic-practice.example", "business_name": "Generic"},
    ]
    actor1 = {"generic-practice.example": ["info@generic-practice.example"]}
    apollo: dict[str, dict[str, str]] = {}
    with_email, without_email = _merge_emails(leads, actor1, apollo)
    assert with_email == []
    assert len(without_email) == 1
    assert without_email[0]["status"] == "suppressed"
    assert "contact_email" not in without_email[0] or not without_email[0].get("contact_email")
