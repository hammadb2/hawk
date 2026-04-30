"""Never-fabricate tests for the HIPAA 2026 control mapper.

The priority list says: *"If no pattern matches, the tag is silently
omitted — never fabricated."* These tests pin that behaviour into CI so a
future refactor can't regress it.
"""

from __future__ import annotations

import re

import pytest

from app.compliance.hipaa_2026 import (
    _COMPILED,
    _CONTROLS,
    _KNOWN_CITATIONS,
    _LAYER_CONTROLS,
    tag_all_findings,
    tag_finding,
)

# ── Spec table from priority list #25 ────────────────────────────────────
#
# Each tuple: (text, expected substring of one citation in the output).
# The mapper may add additional related citations beyond the spec's
# primary one, but the spec primary MUST be present.
SPEC_PRIMARY: list[tuple[str, str]] = [
    ("DMARC policy is none", "164.312(e)(1)"),
    ("SPF record missing", "164.312(e)(2)(ii)"),
    ("DKIM signing not configured", "164.312(e)(2)(ii)"),
    ("MFA not enforced on patient portal login", "164.312(d)"),
    ("Default credentials accepted", "164.312(d)"),
    ("Stealer log breach record found", "164.312(d)"),
    ("TLS 1.0 still enabled", "164.312(e)(1)"),
    ("SSL handshake misconfiguration", "164.312(e)(1)"),
    ("Open RDP port 3389 exposed", "164.312(a)(1)"),
    ("Audit log review missing", "164.312(b)"),
    ("Logging not enabled on auth service", "164.312(b)"),
]


@pytest.mark.parametrize("title,expected_subsection", SPEC_PRIMARY)
def test_spec_primary_subsection_present(title: str, expected_subsection: str) -> None:
    """Each spec finding routes to the spec's primary 164.xxx subsection."""
    finding: dict = {"title": title, "category": "", "description": "", "layer": ""}
    tag_finding(finding)
    cites = finding["compliance"]
    assert any(expected_subsection in c for c in cites), (
        f"{title!r} expected a citation containing {expected_subsection!r}; "
        f"got {cites}"
    )


def test_no_pattern_match_emits_no_citation() -> None:
    """A finding whose blob doesn't match any keyword and whose layer isn't
    in _LAYER_CONTROLS gets an empty compliance list — never a fabricated
    fallback citation."""
    finding: dict = {
        "title": "Some perfectly innocuous text",
        "category": "neutral",
        "description": "Nothing in here that matches any HIPAA keyword.",
        "layer": "totally_unknown_layer_name_xyz",
    }
    tag_finding(finding)
    assert finding["compliance"] == [], (
        "tag_finding emitted citations for a finding that should have "
        f"matched nothing: {finding['compliance']}"
    )


def test_caller_supplied_non_hipaa_tags_are_preserved() -> None:
    """Sibling modules (nvd_cves, vertical_fingerprint) attach non-HIPAA
    compliance tags like 'Vendor patch management' before the mapper
    runs. The mapper's post-filter must NOT drop those — only the
    citations *the mapper itself* added in this call are validated
    against _KNOWN_CITATIONS."""
    finding: dict = {
        "title": "DMARC missing",
        "category": "",
        "description": "",
        "layer": "",
        "compliance": [
            "Vendor patch management",
            "Some other ops tag",
        ],
    }
    tag_finding(finding)
    out = finding["compliance"]
    # Pre-existing tags survive verbatim.
    assert "Vendor patch management" in out
    assert "Some other ops tag" in out
    # Mapper-added DMARC citation is still present.
    assert any("164.312(e)(1)" in c for c in out)


def test_mapper_added_citations_are_in_whitelist() -> None:
    """Run the mapper across a representative finding corpus and assert
    every citation **the mapper added** is in _KNOWN_CITATIONS. (Caller-
    supplied entries from sibling modules are preserved separately.)"""
    findings = [
        {"title": t, "category": "", "description": "", "layer": ""}
        for t, _ in SPEC_PRIMARY
    ]
    findings += [
        {"title": "CVE-2024-1234 in nginx 1.18", "layer": "nvd_supply_chain",
         "compliance": ["Vendor patch management"]},
        {"title": "Subdomain takeover risk", "layer": "subfinder"},
        {"title": "Ransomware group Lockbit recently active", "layer": "ransomware_intel"},
        {"title": "Lookalike domain detected", "layer": "dnstwist"},
        {"title": "GitHub repo has hardcoded API key", "layer": "github"},
    ]
    pre_existing_per_finding = [list(f.get("compliance") or []) for f in findings]
    tag_all_findings(findings)
    for original, f in zip(pre_existing_per_finding, findings):
        out = f.get("compliance", [])
        # Pre-existing entries are preserved (regression guard for the
        # nvd_cves / vertical_fingerprint silent-drop bug).
        for tag in original:
            assert tag in out, (
                f"caller-supplied tag {tag!r} on {f['title']!r} was "
                "silently dropped by the mapper"
            )
        # Anything the mapper added must be in the whitelist.
        added = [c for c in out if c not in original]
        for c in added:
            assert c in _KNOWN_CITATIONS, (
                f"finding {f['title']!r} mapper-emitted citation {c!r} "
                "is not in _KNOWN_CITATIONS — fabrication regression!"
            )


def test_known_citations_all_use_45cfr_format() -> None:
    """Sanity check on the whitelist itself — all citations follow the
    documented '45 CFR §164.xxx — Description' format. Catches typos at
    module load time."""
    pattern = re.compile(r"^45 CFR §164\.[0-9]+(?:\([A-Za-z0-9]+\))+ — .+$")
    for cite in _KNOWN_CITATIONS:
        assert pattern.match(cite), f"malformed citation in whitelist: {cite!r}"


def test_layer_only_match_still_attaches_citation() -> None:
    """A finding with no keyword hits but a known layer (e.g. naabu port
    scan output) still receives the layer's citations."""
    finding: dict = {
        "title": "service detected",
        "category": "",
        "description": "",
        "layer": "naabu",
    }
    tag_finding(finding)
    assert any("164.312(e)(1)" in c for c in finding["compliance"]), (
        f"naabu layer should attach 164.312(e)(1); got {finding['compliance']}"
    )


def test_known_citations_includes_audit_controls() -> None:
    """Spec adds 164.312(b) Audit Controls — confirm it's mappable."""
    assert any("164.312(b)" in c for c in _KNOWN_CITATIONS), (
        "_KNOWN_CITATIONS missing 164.312(b) Audit Controls"
    )


def test_compiled_count_matches_controls() -> None:
    """Sanity: every entry in _CONTROLS produces exactly one compiled regex."""
    assert len(_COMPILED) == len(_CONTROLS)
