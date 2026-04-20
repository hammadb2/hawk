"""Out-of-office reply parser.

Extracts the "I'll be back on X" return date from a free-form OOO auto-reply so
we can schedule our next attempt for that exact day. If no return date is
mentioned we default to 5 business days out — calibrated against the common
"short vacation / parental leave / conference" phrasing.

Pure regex + calendar math. We deliberately do NOT use the LLM for this:
OOO bodies are boilerplate, the dates are usually unambiguous, and the
cost/latency of an LLM call per OOO is wasteful.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _advance_business_days(start: date, days: int) -> date:
    d = start
    added = 0
    while added < days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # Mon–Fri
            added += 1
    return d


def _build_date(year: int | None, month: int, day: int, today: date) -> date | None:
    try:
        candidate = date(year or today.year, month, day)
    except ValueError:
        return None
    # OOO body rarely includes year; if the naive build is in the past, assume next year.
    if year is None and candidate < today - timedelta(days=30):
        try:
            candidate = candidate.replace(year=candidate.year + 1)
        except ValueError:
            return None
    return candidate


_ISO_RE = re.compile(r"\b(20\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12][0-9]|3[01])\b")
_SLASH_RE = re.compile(r"\b(0?[1-9]|1[0-2])[/\-](0?[1-9]|[12][0-9]|3[01])(?:[/\-](20\d{2}))?\b")
_MONTH_DAY_RE = re.compile(
    r"\b(?:"
    + "|".join(_MONTHS.keys())
    + r")\s+([0-3]?\d)(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b",
    re.IGNORECASE,
)
_DAY_MONTH_RE = re.compile(
    r"\b([0-3]?\d)(?:st|nd|rd|th)?\s+(?:of\s+)?("
    + "|".join(_MONTHS.keys())
    + r")(?:,?\s+(20\d{2}))?\b",
    re.IGNORECASE,
)


def extract_return_date(body: str, *, today: date | None = None) -> date | None:
    """Return the most likely back-in-office date, or None if we can't tell."""
    if not body:
        return None
    today = today or datetime.now(timezone.utc).date()

    # Phrase cue: look inside ±80 chars of "back", "return", "until", "through", "after"
    # so we bias toward the date that's actually the return date (vs "I left on Feb 12").
    cue = re.search(
        r"\b(?:back (?:on|in)|returning(?: on)?|i (?:will )?return|until|through|after|out (?:of office|until))\b",
        body,
        re.IGNORECASE,
    )
    if cue:
        start = max(0, cue.start() - 20)
        end = min(len(body), cue.end() + 120)
        snippet = body[start:end]
    else:
        snippet = body

    for m in _ISO_RE.finditer(snippet):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        r = _build_date(y, mo, d, today)
        if r and r >= today:
            return r
    for m in _MONTH_DAY_RE.finditer(snippet):
        month_name = m.group(0).split()[0].lower()
        mo = _MONTHS.get(month_name.rstrip(".,"))
        if not mo:
            continue
        d = int(m.group(1))
        y = int(m.group(2)) if m.group(2) else None
        r = _build_date(y, mo, d, today)
        if r and r >= today:
            return r
    for m in _DAY_MONTH_RE.finditer(snippet):
        d = int(m.group(1))
        mo = _MONTHS.get(m.group(2).lower().rstrip(".,"))
        if not mo:
            continue
        y = int(m.group(3)) if m.group(3) else None
        r = _build_date(y, mo, d, today)
        if r and r >= today:
            return r
    for m in _SLASH_RE.finditer(snippet):
        mo = int(m.group(1))
        d = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else None
        r = _build_date(y, mo, d, today)
        if r and r >= today:
            return r
    return None


def default_followup_date(today: date | None = None, business_days: int = 5) -> date:
    today = today or datetime.now(timezone.utc).date()
    return _advance_business_days(today, business_days)


__all__ = ["extract_return_date", "default_followup_date"]
