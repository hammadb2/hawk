"""HHS OCR breach incident lookup for Charlotte cold-outreach.

Given a prospect's industry + state + scan finding type, return the most
relevant recent real public HIPAA breach to cite in the email body.

Match priority (most specific first):
  1. Same state + matching breach_location (e.g. "email_security" finding
     -> breach_location = 'Email')
  2. Same state, any location
  3. Adjacent state (BEA region) + matching breach_location
  4. National + matching breach_location, latest year
  5. National, latest year (any)

Returns ``None`` if Charlotte's industry isn't HIPAA-covered (e.g. legal,
accounting). Charlotte's existing prompt already strips regulatory framing
in those cases.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# HHS uses these high-level entity types; everything Charlotte targets in the
# medical verticals (Dental, Medical, Physiotherapy, Optometry) maps to
# Healthcare Provider.
HIPAA_INDUSTRIES = {
    "Dental Clinics",
    "Medical Clinics",
    "Physiotherapy",
    "Optometry",
}

# Map a Charlotte scan finding's "layer" (or top-finding category) onto
# the HHS "Location of Breached Information" enum.
FINDING_LOCATION_MAP: dict[str, list[str]] = {
    "email_security": ["Email", "Email, Network Server", "Electronic Medical Record, Email"],
    "dns": ["Email", "Network Server"],
    "tls": ["Network Server"],
    "infra": ["Network Server"],
    "credentials": ["Network Server", "Email"],
    "breach": ["Network Server", "Email"],
    "leak": ["Network Server"],
}

# BEA-style regional groupings — used when no same-state match exists.
ADJACENT_STATES: dict[str, list[str]] = {
    "AL": ["GA", "FL", "TN", "MS"],
    "AK": ["WA"],
    "AZ": ["NM", "NV", "UT", "CA"],
    "AR": ["MO", "TN", "MS", "LA", "TX", "OK"],
    "CA": ["OR", "NV", "AZ"],
    "CO": ["WY", "NE", "KS", "OK", "NM", "UT"],
    "CT": ["NY", "MA", "RI"],
    "DE": ["MD", "PA", "NJ"],
    "FL": ["GA", "AL"],
    "GA": ["FL", "AL", "TN", "NC", "SC"],
    "HI": ["CA"],
    "ID": ["WA", "OR", "NV", "UT", "WY", "MT"],
    "IL": ["WI", "IA", "MO", "KY", "IN"],
    "IN": ["MI", "OH", "KY", "IL"],
    "IA": ["MN", "WI", "IL", "MO", "NE", "SD"],
    "KS": ["NE", "MO", "OK", "CO"],
    "KY": ["IN", "OH", "WV", "VA", "TN", "MO", "IL"],
    "LA": ["TX", "AR", "MS"],
    "ME": ["NH"],
    "MD": ["PA", "DE", "VA", "WV", "DC"],
    "MA": ["NH", "VT", "NY", "CT", "RI"],
    "MI": ["WI", "OH", "IN"],
    "MN": ["ND", "SD", "IA", "WI"],
    "MS": ["TN", "AL", "LA", "AR"],
    "MO": ["IA", "IL", "KY", "TN", "AR", "OK", "KS", "NE"],
    "MT": ["ID", "WY", "SD", "ND"],
    "NE": ["SD", "IA", "MO", "KS", "CO", "WY"],
    "NV": ["OR", "ID", "UT", "AZ", "CA"],
    "NH": ["ME", "VT", "MA"],
    "NJ": ["NY", "PA", "DE"],
    "NM": ["CO", "OK", "TX", "AZ", "UT"],
    "NY": ["VT", "MA", "CT", "NJ", "PA"],
    "NC": ["VA", "TN", "GA", "SC"],
    "ND": ["MN", "SD", "MT"],
    "OH": ["MI", "PA", "WV", "KY", "IN"],
    "OK": ["KS", "MO", "AR", "TX", "NM", "CO"],
    "OR": ["WA", "ID", "NV", "CA"],
    "PA": ["NY", "NJ", "DE", "MD", "WV", "OH"],
    "RI": ["MA", "CT"],
    "SC": ["NC", "GA"],
    "SD": ["ND", "MN", "IA", "NE", "WY", "MT"],
    "TN": ["KY", "VA", "NC", "GA", "AL", "MS", "AR", "MO"],
    "TX": ["NM", "OK", "AR", "LA"],
    "UT": ["ID", "WY", "CO", "NM", "AZ", "NV"],
    "VT": ["NY", "NH", "MA"],
    "VA": ["MD", "DC", "WV", "KY", "TN", "NC"],
    "WA": ["ID", "OR"],
    "WV": ["PA", "MD", "VA", "KY", "OH"],
    "WI": ["MI", "MN", "IA", "IL"],
    "WY": ["MT", "SD", "NE", "CO", "UT", "ID"],
}


def _is_hipaa(industry: str) -> bool:
    if not industry:
        return False
    if industry in HIPAA_INDUSTRIES:
        return True
    lo = industry.lower()
    return any(w in lo for w in ("dental", "medical", "clinic", "physio", "optomet", "health"))


def _finding_locations(finding_layer: str | None) -> list[str]:
    if not finding_layer:
        return []
    key = finding_layer.lower().strip()
    return FINDING_LOCATION_MAP.get(key, [])


def _sb_get(params: dict[str, str]) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SERVICE_KEY:
        return []
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
    }
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(
                f"{SUPABASE_URL}/rest/v1/hhs_ocr_breach_incidents",
                params=params,
                headers=headers,
            )
            if r.status_code >= 400:
                logger.warning("hhs lookup failed status=%s body=%s", r.status_code, r.text[:200])
                return []
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("hhs lookup error: %s", e)
        return []


def lookup_relevant_breach(
    industry: str,
    state: str | None,
    finding_layer: str | None,
    *,
    min_individuals: int = 500,
) -> dict[str, Any] | None:
    """Return the most relevant HHS breach incident for a prospect, or None.

    Charlotte's prompt only injects a citation when this returns a row;
    otherwise the LLM is instructed to skip the trust-signal sentence.
    """
    if not _is_hipaa(industry):
        return None
    state = (state or "").strip().upper() or None
    locations = _finding_locations(finding_layer)
    select = (
        "id,covered_entity_name,state,entity_type,individuals_affected,"
        "breach_submission_date,breach_type,breach_location"
    )
    base = {
        "select": select,
        "entity_type": "eq.Healthcare Provider",
        "individuals_affected": f"gte.{min_individuals}",
        "order": "breach_submission_date.desc",
        "limit": "1",
    }

    def _try(extra: dict[str, str]) -> dict[str, Any] | None:
        rows = _sb_get({**base, **extra})
        return rows[0] if rows else None

    # 1. same state + matching location
    if state and locations:
        for loc in locations:
            row = _try({"state": f"eq.{state}", "breach_location": f"eq.{loc}"})
            if row:
                return row
    # 2. same state, any location
    if state:
        row = _try({"state": f"eq.{state}"})
        if row:
            return row
    # 3. adjacent state + matching location
    if state and locations and state in ADJACENT_STATES:
        adj = ",".join(ADJACENT_STATES[state])
        for loc in locations:
            row = _try({"state": f"in.({adj})", "breach_location": f"eq.{loc}"})
            if row:
                return row
    # 4. national + matching location
    if locations:
        for loc in locations:
            row = _try({"breach_location": f"eq.{loc}"})
            if row:
                return row
    # 5. national any
    return _try({})


def format_citation(breach: dict[str, Any]) -> str:
    """Compose a one-line citation suitable for the LLM prompt context.

    Charlotte then references this verbatim in the email body, prefixed by
    "per the HHS OCR public breach database".
    """
    name = breach.get("covered_entity_name") or "a covered entity"
    state = breach.get("state") or ""
    individuals = breach.get("individuals_affected") or 0
    date = breach.get("breach_submission_date") or ""
    btype = breach.get("breach_type") or ""
    location = breach.get("breach_location") or ""
    year = date.split("-")[0] if date else ""
    indiv_str = f"{int(individuals):,}" if individuals else "an undisclosed number of"
    parts = [f"{name} ({state})" if state else name]
    if year:
        parts.append(f"in {year}")
    parts.append(
        f"via {btype.lower()}" if btype else "via a breach"
    )
    if location:
        parts.append(f"affecting {location.lower()}")
    parts.append(f"impacting {indiv_str} patients")
    return ", ".join(p for p in parts if p)
