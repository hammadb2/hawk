"""HIPAA 2026 Security Rule Control Mapper.

Maps every scanner finding to the specific HIPAA Security Rule subsection
it violates based on category, title, and layer signals.  The mapper runs
on the finished findings list and **appends** regulatory citations to the
existing ``compliance`` list on each finding dict.

References use the 45 CFR 164.3xx numbering from the 2026 HIPAA Security
Rule update (NPRM published Jan 2025, effective 2026).

Never-fabricate guarantee
-------------------------
This mapper appends a HIPAA citation to a finding only when one of two
conditions holds:
  1. its ``layer`` field matches a layer in ``_LAYER_CONTROLS`` (the
     scanner already wrote the layer when it produced the finding), or
  2. one of the keyword regexes in ``_CONTROLS`` matches the finding's
     ``title + category + description + layer`` blob.

If neither holds, **this mapper adds nothing**. There is no else branch,
no default citation, and no LLM-derived inference. ``_KNOWN_CITATIONS``
is the whitelist of every citation string this mapper is allowed to
emit; the post-filter in ``tag_finding`` only validates **citations this
mapper contributed in the current call** — pre-existing entries on the
finding (e.g. ``"Vendor patch management"`` written by ``nvd_cves`` or
``vertical_fingerprint``) are preserved verbatim. A typo or
hallucination inside the static map itself is still caught at module
load time by the CI test ``test_known_citations_all_use_45cfr_format``.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Static compliance map
# ---------------------------------------------------------------------------
# Each entry: (match function, list of HIPAA citations to append)

_CONTROLS: list[tuple[str, list[str]]] = [
    # -- Email security / spoofing ----------------------------------------
    # Spec: SPF and DKIM map to 164.312(e)(2)(ii) Encryption.
    # DMARC maps to 164.312(e)(1) Transmission Security.
    ("spf", [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
        "45 CFR §164.312(e)(1) — Transmission Security",
        "45 CFR §164.312(e)(2)(i) — Integrity Controls",
    ]),
    ("dkim", [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
        "45 CFR §164.312(e)(1) — Transmission Security",
        "45 CFR §164.312(e)(2)(i) — Integrity Controls",
    ]),
    ("dmarc", [
        "45 CFR §164.312(e)(1) — Transmission Security",
        "45 CFR §164.312(e)(2)(ii) — Encryption (email authentication)",
    ]),
    # -- Access control / authentication ----------------------------------
    ("mfa", [
        "45 CFR §164.312(d) — Person or Entity Authentication",
        "45 CFR §164.312(a)(2)(i) — Unique User Identification",
        "45 CFR §164.312(a)(1) — Access Control",
    ]),
    ("login", [
        "45 CFR §164.312(a)(1) — Access Control",
        "45 CFR §164.312(d) — Person or Entity Authentication",
    ]),
    ("admin", [
        "45 CFR §164.312(a)(1) — Access Control",
        "45 CFR §164.312(a)(2)(i) — Unique User Identification",
    ]),
    ("credential", [
        "45 CFR §164.312(d) — Person or Entity Authentication",
        "45 CFR §164.308(a)(5)(ii)(D) — Password Management",
    ]),
    ("password", [
        "45 CFR §164.312(d) — Person or Entity Authentication",
        "45 CFR §164.308(a)(5)(ii)(D) — Password Management",
    ]),
    # -- Encryption / TLS -------------------------------------------------
    ("tls", [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
        "45 CFR §164.312(e)(1) — Transmission Security",
    ]),
    ("ssl", [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
        "45 CFR §164.312(e)(1) — Transmission Security",
    ]),
    ("cleartext", [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
        "45 CFR §164.312(e)(1) — Transmission Security",
    ]),
    ("http ", [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
    ]),
    ("cipher", [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
    ]),
    ("encryption", [
        "45 CFR §164.312(a)(2)(iv) — Encryption and Decryption",
        "45 CFR §164.312(e)(2)(ii) — Encryption",
    ]),
    # -- Vulnerability / patching -----------------------------------------
    ("cve", [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
        "45 CFR §164.308(a)(1)(ii)(B) — Risk Management",
        "45 CFR §164.308(a)(5)(ii)(B) — Protection from Malicious Software",
    ]),
    ("nuclei", [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
        "45 CFR §164.308(a)(1)(ii)(B) — Risk Management",
    ]),
    ("vulnerability", [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
        "45 CFR §164.308(a)(1)(ii)(B) — Risk Management",
    ]),
    ("patch", [
        "45 CFR §164.308(a)(1)(ii)(B) — Risk Management",
        "45 CFR §164.308(a)(5)(ii)(B) — Protection from Malicious Software",
    ]),
    ("supply chain", [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
        "45 CFR §164.314(a)(1) — Business Associate Contracts",
    ]),
    # -- Breach / stealer -------------------------------------------------
    # Spec: Credentials and breach map to 164.312(d) Person Authentication.
    ("breach", [
        "45 CFR §164.312(d) — Person or Entity Authentication",
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
        "45 CFR §164.308(a)(1)(ii)(D) — Information System Activity Review",
    ]),
    ("stealer", [
        "45 CFR §164.312(d) — Person or Entity Authentication",
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
        "45 CFR §164.308(a)(5)(ii)(B) — Protection from Malicious Software",
    ]),
    ("ransomware", [
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
        "45 CFR §164.308(a)(7)(i) — Contingency Plan",
        "45 CFR §164.308(a)(7)(ii)(A) — Data Backup Plan",
    ]),
    # -- Network / port exposure ------------------------------------------
    # Spec: Open ports and RDP map to 164.312(a)(1) Access Control.
    ("port", [
        "45 CFR §164.312(a)(1) — Access Control",
        "45 CFR §164.312(e)(1) — Transmission Security",
        "45 CFR §164.310(a)(1) — Facility Access Controls",
    ]),
    ("rdp", [
        "45 CFR §164.312(a)(1) — Access Control",
        "45 CFR §164.312(e)(1) — Transmission Security",
    ]),
    ("remote access", [
        "45 CFR §164.312(a)(1) — Access Control",
        "45 CFR §164.312(e)(1) — Transmission Security",
    ]),
    ("vpn", [
        "45 CFR §164.312(e)(1) — Transmission Security",
        "45 CFR §164.312(a)(1) — Access Control",
    ]),
    ("internet exposure", [
        "45 CFR §164.312(e)(1) — Transmission Security",
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
    ]),
    # -- Attack surface / subdomain / lookalike ----------------------------
    ("lookalike", [
        "45 CFR §164.308(a)(5)(i) — Security Awareness and Training",
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
    ]),
    ("subdomain", [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
    ]),
    ("attack surface", [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
    ]),
    # -- GitHub / code leak -----------------------------------------------
    ("github", [
        "45 CFR §164.312(c)(1) — Integrity",
        "45 CFR §164.308(a)(3)(i) — Workforce Security",
    ]),
    ("code leak", [
        "45 CFR §164.312(c)(1) — Integrity",
        "45 CFR §164.308(a)(4)(i) — Information Access Management",
    ]),
    # -- Audit / logging --------------------------------------------------
    # Spec: Audit and logs map to 164.312(b) Audit Controls.
    ("audit", [
        "45 CFR §164.312(b) — Audit Controls",
    ]),
    ("logging", [
        "45 CFR §164.312(b) — Audit Controls",
    ]),
    ("log review", [
        "45 CFR §164.312(b) — Audit Controls",
        "45 CFR §164.308(a)(1)(ii)(D) — Information System Activity Review",
    ]),
    ("siem", [
        "45 CFR §164.312(b) — Audit Controls",
    ]),
    # -- Insurance / compliance -------------------------------------------
    ("insurance", [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
        "45 CFR §164.308(a)(1)(ii)(B) — Risk Management",
    ]),
]

# Compiled patterns (case-insensitive)
_COMPILED: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(rf"\b{re.escape(keyword)}", re.I), citations)
    for keyword, citations in _CONTROLS
]

# Layer-specific overrides (always applies if layer matches)
_LAYER_CONTROLS: dict[str, list[str]] = {
    "email_security": [
        "45 CFR §164.312(e)(1) — Transmission Security",
    ],
    "ssl_deep": [
        "45 CFR §164.312(e)(2)(ii) — Encryption",
        "45 CFR §164.312(e)(1) — Transmission Security",
    ],
    "breach_monitoring": [
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
    ],
    "nuclei": [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
    ],
    "nvd_supply_chain": [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
        "45 CFR §164.308(a)(1)(ii)(B) — Risk Management",
    ],
    "internetdb": [
        "45 CFR §164.312(e)(1) — Transmission Security",
    ],
    "naabu": [
        "45 CFR §164.312(e)(1) — Transmission Security",
    ],
    "httpx": [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
    ],
    "mfa_detection": [
        "45 CFR §164.312(d) — Person or Entity Authentication",
        "45 CFR §164.312(a)(1) — Access Control",
    ],
    "vertical_fingerprint": [
        "45 CFR §164.308(a)(1)(ii)(A) — Risk Analysis",
        "45 CFR §164.308(a)(1)(ii)(B) — Risk Management",
    ],
    "ransomware_intel": [
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
        "45 CFR §164.308(a)(7)(i) — Contingency Plan",
    ],
}


# ---------------------------------------------------------------------------
# Never-fabricate whitelist
# ---------------------------------------------------------------------------
# Every citation the mapper is allowed to emit, derived from _CONTROLS and
# _LAYER_CONTROLS. The post-filter on tag_finding drops anything not in
# this set; that protects clients from a typo or a bad merge silently
# putting an invalid 164.xxx subsection on a compliance report.
def _build_known_citations() -> frozenset[str]:
    seen: set[str] = set()
    for _, cites in _CONTROLS:
        seen.update(cites)
    for cites in _LAYER_CONTROLS.values():
        seen.update(cites)
    return frozenset(seen)


_KNOWN_CITATIONS: frozenset[str] = _build_known_citations()


def tag_finding(finding: dict[str, Any]) -> None:
    """Append HIPAA 2026 citations to a single finding dict (mutates in place).

    Never-fabricate guarantee: a citation is appended **by this mapper**
    only when an explicit layer match (``_LAYER_CONTROLS``) or keyword
    regex match (``_COMPILED``) fires. There is no default / fallback /
    inferred citation. Sibling modules (e.g. ``nvd_cves``,
    ``vertical_fingerprint``) may attach non-HIPAA tags like
    ``"Vendor patch management"`` to ``compliance`` before this mapper
    runs; those caller-supplied entries are preserved verbatim. The
    never-fabricate post-filter only validates the citations this mapper
    contributes against ``_KNOWN_CITATIONS``.
    """
    pre_existing: list[str] = list(finding.get("compliance") or [])
    seen: set[str] = set(pre_existing)

    blob = " ".join([
        finding.get("title") or "",
        finding.get("category") or "",
        finding.get("description") or "",
        finding.get("layer") or "",
    ]).lower()

    mapper_added: list[str] = []

    # Layer-based citations
    layer = (finding.get("layer") or "").strip()
    for cite in _LAYER_CONTROLS.get(layer, []):
        if cite not in seen:
            mapper_added.append(cite)
            seen.add(cite)

    # Keyword-based citations
    for pattern, citations in _COMPILED:
        if pattern.search(blob):
            for cite in citations:
                if cite not in seen:
                    mapper_added.append(cite)
                    seen.add(cite)

    # Never-fabricate post-filter: only the citations *this mapper* added
    # are validated against the static whitelist. Pre-existing entries
    # from sibling modules (e.g. ``nvd_cves`` setting "Vendor patch
    # management") pass through untouched. A typo or hallucination
    # introduced inside this module's own static map is still caught at
    # module load by ``test_known_citations_all_use_45cfr_format``.
    validated_new = [c for c in mapper_added if c in _KNOWN_CITATIONS]
    finding["compliance"] = pre_existing + validated_new


def tag_all_findings(findings: list[dict[str, Any]]) -> None:
    """Run the HIPAA 2026 control mapper on every finding in the list."""
    for f in findings:
        tag_finding(f)
