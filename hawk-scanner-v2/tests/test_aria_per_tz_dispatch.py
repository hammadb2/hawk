"""Unit tests for the per-state-timezone dispatch filter (priority list #36).

The rolling dispatcher cron fires hourly 9am–4pm ET. Without per-tz
filtering, a 9am ET tick lands in California prospect inboxes at 6am
Pacific — outside business hours, low reply rate, and (for some
filters) flagged as suspicious. These tests pin the policy:

1. ``state_to_timezone`` maps US state codes to the right IANA zone,
   defaults to ``America/New_York`` for missing/unknown.
2. ``is_state_in_business_hours`` is inclusive on both ends and
   correctly localizes a fixed UTC instant per state.
3. ``_split_in_window`` partitions a fetched batch using each
   prospect's ``province`` field, treating missing province as ET.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------- state_to_timezone --------------------------------------------


@pytest.mark.parametrize(
    "state,expected",
    [
        ("CA", "America/Los_Angeles"),
        ("ca", "America/Los_Angeles"),  # case-insensitive
        ("NY", "America/New_York"),
        ("TX", "America/Chicago"),
        ("CO", "America/Denver"),
        ("AZ", "America/Phoenix"),  # no DST
        ("HI", "Pacific/Honolulu"),
        ("AK", "America/Anchorage"),
        ("PR", "America/Puerto_Rico"),
    ],
)
def test_state_to_timezone_known(state: str, expected: str) -> None:
    from services.state_timezone import state_to_timezone

    assert state_to_timezone(state) == expected


@pytest.mark.parametrize("state", [None, "", "ZZ", "XX", "  "])
def test_state_to_timezone_unknown_defaults_to_eastern(state: str | None) -> None:
    from services.state_timezone import DEFAULT_TZ_NAME, state_to_timezone

    assert state_to_timezone(state) == DEFAULT_TZ_NAME == "America/New_York"


# ---------- is_state_in_business_hours -----------------------------------


# 2024-06-15 17:00 UTC = 1pm Eastern, 12pm Central, 11am Mountain,
# 10am Pacific, 7am Hawaii, 9am Alaska. All US lower-48 are in window.
NOON_ET = datetime(2024, 6, 15, 17, 0, tzinfo=timezone.utc)


def test_in_window_at_noon_eastern_for_lower_48_states() -> None:
    from services.state_timezone import is_state_in_business_hours

    for st in ("NY", "FL", "TX", "CO", "CA", "WA", "AZ"):
        assert is_state_in_business_hours(st, now=NOON_ET) is True, st


# 2024-06-15 13:00 UTC = 9am Eastern, 8am Central, 7am Mountain,
# 6am Pacific. Pacific should be deferred.
NINE_AM_ET = datetime(2024, 6, 15, 13, 0, tzinfo=timezone.utc)


def test_pacific_deferred_when_eastern_just_opens() -> None:
    from services.state_timezone import is_state_in_business_hours

    assert is_state_in_business_hours("NY", now=NINE_AM_ET) is True
    assert is_state_in_business_hours("CA", now=NINE_AM_ET) is False
    assert is_state_in_business_hours("WA", now=NINE_AM_ET) is False


# 2024-06-15 23:00 UTC = 7pm Eastern, 6pm Central, 5pm Mountain,
# 4pm Pacific. Eastern should be deferred (post-window) but Pacific in.
SEVEN_PM_ET = datetime(2024, 6, 15, 23, 0, tzinfo=timezone.utc)


def test_eastern_deferred_when_pacific_still_in_window() -> None:
    from services.state_timezone import is_state_in_business_hours

    assert is_state_in_business_hours("NY", now=SEVEN_PM_ET) is False
    assert is_state_in_business_hours("CA", now=SEVEN_PM_ET) is True


def test_window_inclusive_on_both_ends() -> None:
    """9:00 and 16:00 local should both pass; 8:59 and 17:00 should not."""
    from services.state_timezone import is_state_in_business_hours

    # 9:00 ET exactly
    instant = datetime(2024, 6, 15, 13, 0, tzinfo=timezone.utc)
    assert is_state_in_business_hours("NY", now=instant) is True

    # 8:59 ET — out
    instant = datetime(2024, 6, 15, 12, 59, tzinfo=timezone.utc)
    assert is_state_in_business_hours("NY", now=instant) is False

    # 16:00 ET — in (inclusive)
    instant = datetime(2024, 6, 15, 20, 0, tzinfo=timezone.utc)
    assert is_state_in_business_hours("NY", now=instant) is True

    # 17:00 ET — out
    instant = datetime(2024, 6, 15, 21, 0, tzinfo=timezone.utc)
    assert is_state_in_business_hours("NY", now=instant) is False


def test_unknown_state_uses_eastern_window() -> None:
    """Missing/unknown state falls back to ET — must not silently drop."""
    from services.state_timezone import is_state_in_business_hours

    # 1pm ET → in for ET-default
    assert is_state_in_business_hours(None, now=NOON_ET) is True
    assert is_state_in_business_hours("", now=NOON_ET) is True
    assert is_state_in_business_hours("ZZ", now=NOON_ET) is True

    # 9am ET → in for ET-default but a CA prospect would be out
    assert is_state_in_business_hours(None, now=NINE_AM_ET) is True


# ---------- _split_in_window in the dispatcher ---------------------------


def test_split_in_window_uses_province_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the dispatcher partitions on each row's ``province``."""
    from services import aria_rolling_dispatch as rd
    from services import state_timezone as st

    fixed = NINE_AM_ET  # 9am ET, 6am PT

    # Replace the symbol the dispatcher imported at module-load with a
    # variant that pins "now" — avoids recursion via state_local_now.
    def pinned(state, *, start_hour=9, end_hour=16, now=None):
        return st.is_state_in_business_hours(
            state, start_hour=start_hour, end_hour=end_hour, now=fixed
        )

    monkeypatch.setattr(rd, "is_state_in_business_hours", pinned)

    prospects = [
        {"id": "1", "province": "NY"},
        {"id": "2", "province": "CA"},
        {"id": "3", "province": "FL"},
        {"id": "4", "province": ""},  # missing → defaults to ET → in
        {"id": "5", "province": None},
        {"id": "6", "province": "WA"},
    ]
    in_window, deferred = rd._split_in_window(prospects)

    in_ids = {p["id"] for p in in_window}
    deferred_ids = {p["id"] for p in deferred}
    assert in_ids == {"1", "3", "4", "5"}, in_ids
    assert deferred_ids == {"2", "6"}, deferred_ids
