"""Tests for version-aware NVD CVE matching (priority list #26).

Pins the spec contract into CI:

* WhatWeb output yields exact {tech, version} pairs.
* NVD responses are filtered by CPE version range.
* Findings render in the spec format::

      WordPress 6.4.1 — CVE-2024-4439, CVSS 8.8, patch to 6.5.3

* When no version can be extracted, the fallback finding is low-severity
  ("info") and never says "WordPress has known CVEs".
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.integrations import nvd_cves


# ── Pure helpers ─────────────────────────────────────────────────────────


def test_extract_versioned_techs_bracket_and_slash() -> None:
    lines = [
        "http://x.com [200] WordPress[6.4.1], jQuery[3.6.0]",
        "Server: Apache/2.4.51",
    ]
    out = nvd_cves._extract_versioned_techs(lines)
    pairs = {(it["tech"], it["version"]) for it in out}
    assert ("wordpress", "6.4.1") in pairs
    assert ("jquery", "3.6.0") in pairs
    assert ("apache", "2.4.51") in pairs


def test_version_in_range_inclusive_exclusive() -> None:
    # versionEndExcluding=6.5.3 means 6.5.3 is *fixed*; 6.4.1 is vulnerable.
    assert nvd_cves._version_in_range("6.4.1", None, None, None, "6.5.3") is True
    assert nvd_cves._version_in_range("6.5.3", None, None, None, "6.5.3") is False
    assert nvd_cves._version_in_range("6.5.4", None, None, None, "6.5.3") is False
    # versionStartIncluding=6.0 + versionEndIncluding=6.5
    assert nvd_cves._version_in_range("6.3", "6.0", None, "6.5", None) is True
    assert nvd_cves._version_in_range("5.9", "6.0", None, "6.5", None) is False


def test_max_version_picks_largest_semver() -> None:
    assert nvd_cves._max_version(["6.5.3", "6.4.9", "6.6.0"]) == "6.6.0"
    assert nvd_cves._max_version(["1.2", "1.10"]) == "1.10"  # numeric, not lexical
    assert nvd_cves._max_version([]) is None


def test_severity_derived_from_cvss() -> None:
    assert nvd_cves._severity_from_cvss(9.8) == "critical"
    assert nvd_cves._severity_from_cvss(7.5) == "high"
    assert nvd_cves._severity_from_cvss(5.0) == "medium"
    assert nvd_cves._severity_from_cvss(3.1) == "low"
    assert nvd_cves._severity_from_cvss(None) == "medium"


# ── Finding rendering ─────────────────────────────────────────────────────


def test_build_versioned_finding_matches_spec_format() -> None:
    """Spec: 'WordPress 6.4.1 — CVE-2024-4439, CVSS 8.8, patch to 6.5.3'."""
    matches = [
        {"cve_id": "CVE-2024-4439", "cvss_score": 8.8, "cvss_vector": "AV:N",
         "fix_version": "6.5.3"},
        {"cve_id": "CVE-2024-0001", "cvss_score": 5.4, "cvss_vector": "",
         "fix_version": "6.4.9"},
    ]
    f = nvd_cves._build_versioned_finding(
        label="WordPress", version="6.4.1", domain="example.com", matches=matches,
    )
    # Headline hits the spec template verbatim.
    assert f["title"].startswith("WordPress 6.4.1 — CVE-2024-4439, CVSS 8.8")
    assert "patch to 6.5.3" in f["title"]  # max(6.5.3, 6.4.9) = 6.5.3
    # Structured fields present.
    assert f["severity"] == "high"  # 8.8 → high
    assert f["category"] == "Supply chain"
    assert f["affected_asset"] == "example.com"
    assert "Vendor patch management" in f["compliance"]
    # Technical detail lists every CVE with score + patch.
    assert "CVE-2024-4439 — CVSS 8.8 — patch to 6.5.3" in f["technical_detail"]
    assert "CVE-2024-0001 — CVSS 5.4 — patch to 6.4.9" in f["technical_detail"]
    # Description names version + top CVE + upgrade target.
    assert "WordPress 6.4.1" in f["description"]
    assert "CVE-2024-4439" in f["description"]
    assert "Upgrade to 6.5.3" in f["description"]


def test_build_versioned_finding_no_fix_still_renders() -> None:
    matches = [
        {"cve_id": "CVE-2024-9999", "cvss_score": 9.1, "cvss_vector": "",
         "fix_version": None},
    ]
    f = nvd_cves._build_versioned_finding(
        label="OpenSSL", version="3.0.1", domain="example.com", matches=matches,
    )
    # Headline still present, just without 'patch to X'.
    assert f["title"].startswith("OpenSSL 3.0.1 — CVE-2024-9999, CVSS 9.1")
    assert "patch to" not in f["title"]
    assert f["severity"] == "critical"  # 9.1 ≥ 9.0


def test_unknown_version_finding_is_informational_not_known_cves() -> None:
    """Spec: never emit 'WordPress has known CVEs'. Must say version unknown."""
    f = nvd_cves._build_unknown_version_finding(
        "WordPress", "example.com", ["CVE-2024-0001", "CVE-2024-0002"],
    )
    assert f["severity"] == "info"
    assert "version unknown" in f["title"].lower()
    # Spec: description must NOT be a generic "has known CVEs" claim.
    lowered = (f["description"] + " " + f["title"]).lower()
    assert "has known cves" not in lowered
    assert "wordpress" in lowered


# ── End-to-end via mocked NVD ─────────────────────────────────────────────


def _fake_nvd_response(cves: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal NVD-shaped JSON payload."""
    return {
        "vulnerabilities": [
            {
                "cve": {
                    "id": c["id"],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": c["score"],
                                          "vectorString": "AV:N/AC:L"}}
                        ]
                    } if c.get("score") is not None else {},
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "cpeMatch": [
                                        {
                                            "vulnerable": True,
                                            "criteria": c["criteria"],
                                            **({"versionStartIncluding": c["start_inc"]}
                                               if c.get("start_inc") else {}),
                                            **({"versionEndExcluding": c["end_exc"]}
                                               if c.get("end_exc") else {}),
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                }
            }
            for c in cves
        ]
    }


class _FakeResp:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def get(self, *a: Any, **kw: Any) -> _FakeResp:
        return self._resp


@pytest.mark.asyncio
async def test_versioned_search_filters_by_cpe_range() -> None:
    """6.4.1 should match a CVE with versionEndExcluding=6.5.3 but NOT
    one with versionEndExcluding=6.4.0 (already patched before 6.4.1)."""
    payload = _fake_nvd_response([
        {"id": "CVE-2024-4439", "score": 8.8,
         "criteria": "cpe:2.3:a:wordpress:wordpress:-:*:*:*:*:*:*:*",
         "end_exc": "6.5.3"},
        {"id": "CVE-2023-OLD", "score": 7.5,
         "criteria": "cpe:2.3:a:wordpress:wordpress:-:*:*:*:*:*:*:*",
         "end_exc": "6.4.0"},  # already fixed before 6.4.1
    ])
    with patch.object(nvd_cves.httpx, "AsyncClient",
                      return_value=_FakeClient(_FakeResp(payload))):
        from app.settings import Settings
        matches = await nvd_cves._nvd_versioned_search(
            "wordpress", "6.4.1", "WordPress", Settings(),
        )
    ids = [m["cve_id"] for m in matches]
    assert "CVE-2024-4439" in ids
    assert "CVE-2023-OLD" not in ids


@pytest.mark.asyncio
async def test_per_cve_fix_version_takes_max_of_overlapping_ranges() -> None:
    """Per-CVE fix must escape every matching affected range.

    Regression guard for the Devin Review flag on PR #75: when one CVE
    has two overlapping vulnerable ranges that both cover the detected
    version (e.g. ``[6.0, 6.5.3)`` AND ``[6.0, 6.8.0)`` both cover 6.4.1),
    upgrading to 6.5.3 would still leave the second range triggered.
    Only max(versionEndExcluding) escapes every matching range.
    """
    payload = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2024-OVERLAP",
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.0, "vectorString": ""}}
                        ]
                    },
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "cpeMatch": [
                                        {
                                            "vulnerable": True,
                                            "criteria": (
                                                "cpe:2.3:a:wordpress:wordpress:"
                                                "-:*:*:*:*:*:*:*"
                                            ),
                                            "versionStartIncluding": "6.0",
                                            "versionEndExcluding": "6.5.3",
                                        },
                                        {
                                            "vulnerable": True,
                                            "criteria": (
                                                "cpe:2.3:a:wordpress:wordpress:"
                                                "-:*:*:*:*:*:*:*"
                                            ),
                                            "versionStartIncluding": "6.0",
                                            "versionEndExcluding": "6.8.0",
                                        },
                                    ]
                                }
                            ]
                        }
                    ],
                }
            }
        ]
    }
    with patch.object(nvd_cves.httpx, "AsyncClient",
                      return_value=_FakeClient(_FakeResp(payload))):
        from app.settings import Settings
        matches = await nvd_cves._nvd_versioned_search(
            "wordpress", "6.4.1", "WordPress", Settings(),
        )
    assert matches, "overlapping ranges should still produce a match"
    assert matches[0]["fix_version"] == "6.8.0", (
        "per-CVE fix must escape every matching range; picking 6.5.3 would "
        "leave [6.0, 6.8.0) still vulnerable"
    )


@pytest.mark.asyncio
async def test_end_to_end_emits_spec_format_finding() -> None:
    """Full pipeline from WhatWeb lines → mocked NVD → spec-format finding."""
    payload = _fake_nvd_response([
        {"id": "CVE-2024-4439", "score": 8.8,
         "criteria": "cpe:2.3:a:wordpress:wordpress:-:*:*:*:*:*:*:*",
         "end_exc": "6.5.3"},
    ])
    with patch.object(nvd_cves.httpx, "AsyncClient",
                      return_value=_FakeClient(_FakeResp(payload))):
        findings = await nvd_cves.nvd_findings_from_whatweb(
            ["http://example.com [200] WordPress[6.4.1]"],
            "example.com",
        )
    assert len(findings) >= 1
    wp = next(f for f in findings if "WordPress 6.4.1" in f["title"])
    assert "CVE-2024-4439" in wp["title"]
    assert "CVSS 8.8" in wp["title"]
    assert "patch to 6.5.3" in wp["title"]
    assert wp["severity"] == "high"
    assert wp["layer"] == "nvd_supply_chain"
    # Never the vague "known CVEs" wording.
    assert "has known cves" not in (wp["title"] + wp["description"]).lower()


@pytest.mark.asyncio
async def test_fallback_is_informational_not_generic() -> None:
    """When WhatWeb exposes no version, we must NOT say 'WordPress has known CVEs'."""
    # No versioned techs in the input, so only the keyword search runs.
    keyword_payload = {
        "vulnerabilities": [
            {"cve": {"id": "CVE-2024-AAAA"}},
            {"cve": {"id": "CVE-2024-BBBB"}},
        ]
    }

    with patch.object(nvd_cves.httpx, "AsyncClient",
                      return_value=_FakeClient(_FakeResp(keyword_payload))):
        findings = await nvd_cves.nvd_findings_from_whatweb(
            # WordPress keyword visible, no version bracket.
            ["http://x.com [200] WordPress blog"],
            "x.com",
        )
    # Fallback finding exists, is info-severity, and phrased precisely.
    assert any(f["severity"] == "info" for f in findings), findings
    for f in findings:
        blob = (f["title"] + " " + f["description"]).lower()
        assert "has known cves" not in blob
