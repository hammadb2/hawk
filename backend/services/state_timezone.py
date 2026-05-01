"""Map US state codes → IANA timezone names + per-state business-hours check.

Used by the ARIA rolling dispatcher (priority list item #36) so a prospect
in California isn't emailed at 6am their local time just because the
dispatcher cron fires at 9am Eastern.

Multi-zone states (Alaska, Florida, Idaho, Indiana, Kansas, Kentucky,
Michigan, Nebraska, North Dakota, Oregon, South Dakota, Tennessee, Texas)
collapse to the **majority** zone for that state — the alternative would
be requiring per-county data we don't have. Worst-case error is one hour
either side of the send window for prospects in the minority zone, which
is acceptable for outbound at +/- 9am.

Domestic territories (PR/VI/GU/MP/AS) and DC are included so the picker
doesn't accidentally drop them; if a state code we don't recognize comes
in we fall back to ``America/New_York`` (the dispatcher's historical
behavior, see ``aria_rolling_dispatch.DISPATCH_TZ``).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

# Default for unknown / missing state — matches the dispatcher's historical anchor.
DEFAULT_TZ_NAME = "America/New_York"

# State → IANA timezone (majority zone where the state spans more than one).
STATE_TZ: dict[str, str] = {
    # Eastern
    "CT": "America/New_York",
    "DE": "America/New_York",
    "DC": "America/New_York",
    "GA": "America/New_York",
    "ME": "America/New_York",
    "MD": "America/New_York",
    "MA": "America/New_York",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NY": "America/New_York",
    "NC": "America/New_York",
    "OH": "America/New_York",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "VT": "America/New_York",
    "VA": "America/New_York",
    "WV": "America/New_York",
    # Mostly Eastern (Florida panhandle is Central; majority is Eastern).
    "FL": "America/New_York",
    # Mostly Eastern (a few western counties are Central).
    "MI": "America/New_York",
    "IN": "America/New_York",
    "KY": "America/New_York",
    "TN": "America/Chicago",  # Central majority (Memphis, Nashville)
    # Central
    "AL": "America/Chicago",
    "AR": "America/Chicago",
    "IL": "America/Chicago",
    "IA": "America/Chicago",
    "LA": "America/Chicago",
    "MN": "America/Chicago",
    "MS": "America/Chicago",
    "MO": "America/Chicago",
    "OK": "America/Chicago",
    "WI": "America/Chicago",
    # Mostly Central (Texas: El Paso is Mountain; majority is Central).
    "TX": "America/Chicago",
    # Mostly Central.
    "KS": "America/Chicago",
    "NE": "America/Chicago",
    "ND": "America/Chicago",
    "SD": "America/Chicago",
    # Mountain
    "CO": "America/Denver",
    "MT": "America/Denver",
    "NM": "America/Denver",
    "UT": "America/Denver",
    "WY": "America/Denver",
    # Arizona observes MST year-round (no DST).
    "AZ": "America/Phoenix",
    # Mostly Mountain.
    "ID": "America/Denver",
    # Pacific
    "CA": "America/Los_Angeles",
    "NV": "America/Los_Angeles",
    "WA": "America/Los_Angeles",
    # Mostly Pacific (Malheur County is Mountain).
    "OR": "America/Los_Angeles",
    # Alaska majority
    "AK": "America/Anchorage",
    # Hawaii (no DST).
    "HI": "Pacific/Honolulu",
    # Territories — non-contiguous but the picker shouldn't drop these silently.
    "PR": "America/Puerto_Rico",
    "VI": "America/St_Thomas",
    "GU": "Pacific/Guam",
    "MP": "Pacific/Saipan",
    "AS": "Pacific/Pago_Pago",
}


def state_to_timezone(state_code: str | None) -> str:
    """Return the IANA timezone name for a US state code (default ET)."""
    if not state_code:
        return DEFAULT_TZ_NAME
    return STATE_TZ.get(state_code.strip().upper(), DEFAULT_TZ_NAME)


def state_local_now(state_code: str | None, *, now: datetime | None = None) -> datetime:
    """Return ``now`` (UTC) localized to the state's IANA timezone.

    ``now`` defaults to ``datetime.now(timezone.utc)`` and exists only so
    tests can pin time deterministically.
    """
    from datetime import timezone as _tz

    instant = now if now is not None else datetime.now(_tz.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=_tz.utc)
    return instant.astimezone(ZoneInfo(state_to_timezone(state_code)))


def is_state_in_business_hours(
    state_code: str | None,
    *,
    start_hour: int = 9,
    end_hour: int = 16,
    now: datetime | None = None,
) -> bool:
    """True iff the state's local hour is in ``[start_hour, end_hour]`` inclusive.

    The window is **inclusive** on both ends to match the existing
    ``DISPATCH_TICK_HOURS`` pattern in ``aria_rolling_dispatch`` (9, 10,
    …, 16). A 4pm tick still gets to send.
    """
    local_now = state_local_now(state_code, now=now)
    return start_hour <= local_now.hour <= end_hour
