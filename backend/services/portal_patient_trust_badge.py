"""Patient Trust Badge — for healthcare-vertical clients to display
publicly that their data handling has been verified by HAWK (priority
list item #38).

Distinct from the generic HAWK Certified badge in
``routers.portal_phase2`` because:

* It targets the **patient/customer** as the audience, not the buyer.
  The wording ("Patient Data Protected · HIPAA-Aligned Security") is
  meaningful to a patient walking into a waiting room or visiting the
  practice's website; "HAWK Certified" is meaningful to the practice.
* It's only available to **healthcare verticals** (dental, medical,
  pharmacy, mental_health, optometry, chiropractic, physical_therapy)
  — the language references HIPAA so it would mislead a non-covered
  entity to display it.
* The eligibility threshold is looser than the full HAWK Certified
  flow: insurance-readiness ≥ 80% **or** ``certified_at`` set. The
  rationale is that a clinic can earn the patient-facing badge as soon
  as their objective scan-based posture clears the insurance bar, even
  if they haven't completed every step of the 7-step certified path.

Pure module — no httpx/Supabase — so unit tests can pin SVG output and
eligibility logic in milliseconds without spinning up the API.
"""

from __future__ import annotations

import html as html_mod
from typing import Any, Iterable

# Only these verticals see the badge — the wording references HIPAA.
HEALTHCARE_VERTICALS: frozenset[str] = frozenset(
    {
        "dental",
        "medical",
        "pharmacy",
        "mental_health",
        "optometry",
        "chiropractic",
        "physical_therapy",
    }
)

# Looser bar than the HAWK Certified 7-step path: a clinic can earn
# the patient-facing badge as soon as their insurance-readiness is in
# the "ready" tier. ``hawk_readiness_score`` on ``clients`` mirrors the
# scan finding's ``readiness_pct`` so we accept either source.
PATIENT_TRUST_READINESS_FLOOR: int = 80


def _normalize_vertical(raw: str | None) -> str:
    return (raw or "").strip().lower()


def is_healthcare_vertical(industry: str | None) -> bool:
    """Strict membership check — keep substring magic out of eligibility.

    ``aria_post_scan_pipeline`` writes a normalized vertical key so we
    expect an exact match. A loose ``"medical" in raw`` would have let
    "biomedical_supply" earn a HIPAA badge it has no business showing.
    """
    return _normalize_vertical(industry) in HEALTHCARE_VERTICALS


def _readiness_pct_from_scan(scan: dict[str, Any] | None) -> int | None:
    """Mirror of ``services.portal_milestones._insurance_readiness_pct``.

    Duplicated locally so this module stays import-free of
    ``portal_milestones`` (which pulls in scan helpers we don't need).
    """
    if not isinstance(scan, dict):
        return None
    for container_key in ("findings", "raw_layers"):
        container = scan.get(container_key)
        if not isinstance(container, dict):
            continue
        ins = container.get("insurance_readiness")
        if isinstance(ins, dict):
            for key in ("readiness_pct", "score", "overall", "pct"):
                pct = ins.get(key)
                if pct is None:
                    continue
                if isinstance(pct, (int, float)):
                    return int(pct)
                try:
                    return int(pct)
                except (TypeError, ValueError):
                    break
        elif isinstance(ins, (int, float)):
            return int(ins)
    return None


def patient_trust_eligibility(bundle: dict[str, Any] | None) -> dict[str, Any]:
    """Decide whether ``bundle`` qualifies for the patient-trust badge.

    Returns a structured response so the API and the UI both know not
    just *whether* the client is eligible but *why not* if they're
    blocked — without leaking internal scan details.
    """
    if not isinstance(bundle, dict):
        return {
            "eligible": False,
            "reason": "no_portal_profile",
            "vertical": None,
            "readiness_pct": None,
            "certified_at": None,
        }

    prospect = bundle.get("prospect") or {}
    client = bundle.get("client") or {}
    scan = bundle.get("scan") or {}

    industry = str(prospect.get("industry") or scan.get("industry") or "")
    is_health = is_healthcare_vertical(industry)
    certified_at = client.get("certified_at")

    readiness = _readiness_pct_from_scan(scan)
    if readiness is None:
        # Fall back to the cached aggregate on ``clients.hawk_readiness_score``
        # — same number, just precomputed.
        cached = client.get("hawk_readiness_score")
        if isinstance(cached, (int, float)):
            readiness = int(cached)

    out: dict[str, Any] = {
        "eligible": False,
        "reason": None,
        "vertical": _normalize_vertical(industry),
        "readiness_pct": readiness,
        "certified_at": certified_at,
        "readiness_floor": PATIENT_TRUST_READINESS_FLOOR,
    }

    if not is_health:
        out["reason"] = "not_healthcare_vertical"
        return out
    if certified_at:
        out["eligible"] = True
        out["reason"] = "hawk_certified"
        return out
    if readiness is not None and readiness >= PATIENT_TRUST_READINESS_FLOOR:
        out["eligible"] = True
        out["reason"] = "insurance_readiness_above_floor"
        return out
    out["reason"] = "below_readiness_floor"
    return out


def render_patient_trust_badge_svg(
    *,
    company_name: str,
    earned_on: str | None = None,
) -> str:
    """Render the badge as SVG — pure function for trivial testing.

    Distinct visual identity from the HAWK Certified badge:
    medical-green palette, "Patient Data Protected" heading, and a
    HIPAA-alignment subline. Same overall shape (600×380 rounded
    rectangle) so it slots into the same embed sizes a clinic might use
    for the certified badge.
    """
    safe_company = html_mod.escape((company_name or "Your practice")[:64])
    safe_date = html_mod.escape((earned_on or "")[:32])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="380" '
        'viewBox="0 0 600 380" role="img" '
        'aria-label="HAWK Patient Trust Badge — patient data protected">'
        '<defs>'
        '<linearGradient id="ptb-bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#03110a"/>'
        '<stop offset="1" stop-color="#0a2418"/>'
        '</linearGradient>'
        '</defs>'
        '<rect width="600" height="380" rx="24" fill="url(#ptb-bg)"/>'
        '<rect x="10" y="10" width="580" height="360" rx="20" fill="none" '
        'stroke="#00C48C" stroke-width="2"/>'
        # HAWK monogram "shield" icon — small geometric mark, not the full logo.
        '<path d="M300 56 L322 70 L322 102 Q322 124 300 138 Q278 124 278 102 L278 70 Z" '
        'fill="none" stroke="#00C48C" stroke-width="2.4"/>'
        '<path d="M291 100 L298 108 L312 92" fill="none" stroke="#00C48C" '
        'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
        # Heading
        '<text x="300" y="172" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="26" fill="#ffffff" font-weight="800" letter-spacing="0.5">'
        'PATIENT DATA PROTECTED'
        '</text>'
        '<text x="300" y="202" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="13" fill="#6FE7C2" font-weight="600" letter-spacing="3">'
        'HIPAA-ALIGNED SECURITY · MONITORED BY HAWK'
        '</text>'
        # Practice name
        '<text x="300" y="252" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="20" fill="#cbd5e1" font-weight="500">'
        f'{safe_company}'
        '</text>'
        # Earned-on label and date
        '<text x="300" y="298" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="11" letter-spacing="3" fill="#94a3b8">'
        'EARNED'
        '</text>'
        '<text x="300" y="320" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="16" fill="#ffffff" font-weight="600">'
        f'{safe_date}'
        '</text>'
        '<text x="300" y="354" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="11" fill="#64748b">'
        'securedbyhawk.com · verify at securedbyhawk.com/verify'
        '</text>'
        '</svg>'
    )


def embed_snippets(
    *,
    badge_url: str,
    verify_url: str,
    company_name: str,
) -> dict[str, str]:
    """Return ready-to-copy snippets the practice can paste into their site.

    Both the ``badge_url`` and ``verify_url`` are HTML-escaped before
    interpolation; the practice name is HTML-escaped *inside* the alt
    text so a clinic with an apostrophe in its name doesn't produce
    broken HTML.
    """
    bu = html_mod.escape(badge_url, quote=True)
    vu = html_mod.escape(verify_url, quote=True)
    alt = html_mod.escape(
        f"HAWK Patient Trust Badge — {company_name or 'this practice'}",
        quote=True,
    )
    html_block = (
        f'<a href="{vu}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="Verify HAWK Patient Trust">'
        f'<img src="{bu}" alt="{alt}" width="240" height="152" '
        f'style="border:0;max-width:100%;height:auto" />'
        f"</a>"
    )
    return {
        "html": html_block,
        "image_url": badge_url,
        "verify_url": verify_url,
    }
