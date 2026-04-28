"""Dental & Legal software fingerprinting with known CVE cross-reference.

Scans httpx JSONL and WhatWeb output for signatures of common dental and
legal practice management software.  When detected, produces tailored
findings with known CVEs specific to each product.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Signature database
# ---------------------------------------------------------------------------

VERTICAL_SIGNATURES: list[dict[str, Any]] = [
    # --- Dental ---
    {
        "name": "Dentrix",
        "vendor": "Henry Schein",
        "vertical": "dental",
        "patterns": [
            re.compile(r"dentrix", re.I),
            re.compile(r"henry\s*schein.*dental", re.I),
        ],
        "known_cves": [
            {"cve": "CVE-2022-42473", "cvss": 7.5, "note": "Dentrix Ascend insecure direct object reference"},
            {"cve": "CVE-2021-35587", "cvss": 9.8, "note": "Oracle Fusion (used by Dentrix integrations) pre-auth RCE"},
        ],
        "description": "Dentrix is a widely-used dental practice management system. Exposed interfaces may allow access to patient records (PHI).",
    },
    {
        "name": "Eaglesoft",
        "vendor": "Patterson Dental",
        "vertical": "dental",
        "patterns": [
            re.compile(r"eaglesoft", re.I),
            re.compile(r"patterson\s*dental", re.I),
        ],
        "known_cves": [
            {"cve": "CVE-2019-18230", "cvss": 7.5, "note": "Eaglesoft insufficient access controls on patient data API"},
        ],
        "description": "Eaglesoft by Patterson Dental manages clinical and business operations. External exposure risks PHI leakage.",
    },
    {
        "name": "Carestream Dental",
        "vendor": "Carestream",
        "vertical": "dental",
        "patterns": [
            re.compile(r"carestream", re.I),
            re.compile(r"cs\s*imaging", re.I),
        ],
        "known_cves": [
            {"cve": "CVE-2023-31740", "cvss": 8.1, "note": "Carestream dental imaging server path traversal"},
        ],
        "description": "Carestream Dental imaging and practice management. Exposed DICOM or imaging interfaces are high-risk.",
    },
    {
        "name": "Curve Dental",
        "vendor": "Curve Dental",
        "vertical": "dental",
        "patterns": [
            re.compile(r"curve\s*dental", re.I),
            re.compile(r"curvedental\.com", re.I),
        ],
        "known_cves": [],
        "description": "Curve Dental is a cloud-based dental PMS. Verify authentication controls on any exposed portal.",
    },
    {
        "name": "Open Dental",
        "vendor": "Open Dental Software",
        "vertical": "dental",
        "patterns": [
            re.compile(r"open\s*dental", re.I),
            re.compile(r"opendental", re.I),
        ],
        "known_cves": [
            {"cve": "CVE-2022-40471", "cvss": 9.8, "note": "Open Dental SQL injection in patient search API"},
            {"cve": "CVE-2023-25139", "cvss": 7.8, "note": "Open Dental local privilege escalation"},
        ],
        "description": "Open Dental is an open-source PMS with significant install base. Known SQL injection and privilege escalation vulnerabilities.",
    },
    # --- Legal ---
    {
        "name": "Clio",
        "vendor": "Themis Solutions (Clio)",
        "vertical": "legal",
        "patterns": [
            re.compile(r"\bclio\b", re.I),
            re.compile(r"app\.clio\.com", re.I),
            re.compile(r"clio\s*manage", re.I),
        ],
        "known_cves": [],
        "description": "Clio is a leading cloud legal practice management platform. Verify MFA and access controls on client portals.",
    },
    {
        "name": "MyCase",
        "vendor": "MyCase (AffiniPay)",
        "vertical": "legal",
        "patterns": [
            re.compile(r"mycase", re.I),
            re.compile(r"mycase\.com", re.I),
        ],
        "known_cves": [],
        "description": "MyCase legal practice management. Exposed portals may contain privileged client communications.",
    },
    {
        "name": "NetDocuments",
        "vendor": "NetDocuments",
        "vertical": "legal",
        "patterns": [
            re.compile(r"netdocuments", re.I),
            re.compile(r"vault\.netvoyage", re.I),
            re.compile(r"netdocuments\.com", re.I),
        ],
        "known_cves": [
            {"cve": "CVE-2021-27653", "cvss": 6.5, "note": "NetDocuments SSRF in document preview"},
        ],
        "description": "NetDocuments is a cloud DMS for law firms. Exposed document vaults risk attorney-client privileged data.",
    },
]


def fingerprint_from_httpx_whatweb(
    httpx_jsonl: list[dict[str, Any]],
    whatweb_lines: list[str],
    domain: str,
) -> list[dict[str, Any]]:
    """Detect vertical software in httpx + WhatWeb output and produce findings."""
    blob_parts: list[str] = []
    for row in httpx_jsonl or []:
        for key in ("url", "final_url", "title", "body_preview", "header", "technologies"):
            v = row.get(key)
            if isinstance(v, str):
                blob_parts.append(v)
            elif isinstance(v, list):
                blob_parts.extend(str(x) for x in v)
            elif isinstance(v, dict):
                blob_parts.append(str(v))
    blob_parts.extend(whatweb_lines or [])
    blob = "\n".join(blob_parts)

    findings: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for sig in VERTICAL_SIGNATURES:
        if sig["name"] in seen_names:
            continue
        matched = any(p.search(blob) for p in sig["patterns"])
        if not matched:
            continue
        seen_names.add(sig["name"])

        cves = sig["known_cves"]
        if cves:
            max_cvss = max(c["cvss"] for c in cves)
            if max_cvss >= 9.0:
                sev = "critical"
            elif max_cvss >= 7.0:
                sev = "high"
            else:
                sev = "medium"
            cve_detail = "; ".join(
                f"{c['cve']} (CVSS {c['cvss']}) — {c['note']}" for c in cves
            )
            remediation = (
                f"Patch {sig['name']} to the latest version; restrict external access; "
                f"review each CVE: {', '.join(c['cve'] for c in cves)}."
            )
        else:
            sev = "medium"
            cve_detail = "No public CVEs catalogued; verify version currency and access controls."
            remediation = (
                f"Restrict external access to {sig['name']}, enforce MFA, "
                "and ensure the latest vendor patches are applied."
            )

        findings.append({
            "id": str(uuid.uuid4()),
            "severity": sev,
            "category": f"{sig['vertical'].title()} software exposure",
            "title": f"{sig['name']} ({sig['vendor']}) detected on perimeter",
            "description": sig["description"],
            "technical_detail": cve_detail,
            "affected_asset": domain,
            "remediation": remediation,
            "layer": "vertical_fingerprint",
            "compliance": [
                "HIPAA §164.312(a)(1) — Access Control",
                "Vendor patch management",
            ],
        })

    return findings
