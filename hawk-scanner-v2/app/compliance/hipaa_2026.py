"""HIPAA 2026 Security Rule Control Mapper.

Maps every scanner finding to the specific HIPAA Security Rule subsection
it violates based on category, title, and layer signals.  The mapper runs
on the finished findings list and **appends** regulatory citations to the
existing ``compliance`` list on each finding dict.

References use the 45 CFR 164.3xx numbering from the 2026 HIPAA Security
Rule update (NPRM published Jan 2025, effective 2026).
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
    ("spf", [
        "45 CFR §164.312(e)(1) — Transmission Security",
        "45 CFR §164.312(e)(2)(i) — Integrity Controls",
    ]),
    ("dkim", [
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
    ("breach", [
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
        "45 CFR §164.308(a)(1)(ii)(D) — Information System Activity Review",
    ]),
    ("stealer", [
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
        "45 CFR §164.308(a)(5)(ii)(B) — Protection from Malicious Software",
    ]),
    ("ransomware", [
        "45 CFR §164.308(a)(6)(ii) — Response and Reporting",
        "45 CFR §164.308(a)(7)(i) — Contingency Plan",
        "45 CFR §164.308(a)(7)(ii)(A) — Data Backup Plan",
    ]),
    # -- Network / port exposure ------------------------------------------
    ("port", [
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


def tag_finding(finding: dict[str, Any]) -> None:
    """Append HIPAA 2026 citations to a single finding dict (mutates in place)."""
    compliance: list[str] = finding.get("compliance") or []

    blob = " ".join([
        finding.get("title") or "",
        finding.get("category") or "",
        finding.get("description") or "",
        finding.get("layer") or "",
    ]).lower()

    added: set[str] = set(compliance)

    # Layer-based citations
    layer = (finding.get("layer") or "").strip()
    for cite in _LAYER_CONTROLS.get(layer, []):
        if cite not in added:
            compliance.append(cite)
            added.add(cite)

    # Keyword-based citations
    for pattern, citations in _COMPILED:
        if pattern.search(blob):
            for cite in citations:
                if cite not in added:
                    compliance.append(cite)
                    added.add(cite)

    finding["compliance"] = compliance


def tag_all_findings(findings: list[dict[str, Any]]) -> None:
    """Run the HIPAA 2026 control mapper on every finding in the list."""
    for f in findings:
        tag_finding(f)
