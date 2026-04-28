"""Cyber Insurance Readiness Score.

Standalone module that runs on the same scan data as the HAWK Score and
produces a separate percentage calibrated to what underwriters check:

  - MFA presence
  - SPF / DKIM / DMARC enforcement
  - Exposed RDP or remote access ports
  - Breach history
  - Patch currency (CVE findings)
  - Open ports

The output tells the prospect their readiness percentage and what specific
fixes would improve their insurability.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Weighted control checks (sum of weights = 100)
# ---------------------------------------------------------------------------
_CONTROLS: list[dict[str, Any]] = [
    {"key": "mfa",         "weight": 20, "label": "Multi-Factor Authentication (MFA)"},
    {"key": "spf",         "weight": 10, "label": "SPF email authentication"},
    {"key": "dkim",        "weight":  5, "label": "DKIM email signing"},
    {"key": "dmarc",       "weight": 10, "label": "DMARC policy enforcement"},
    {"key": "encryption",  "weight": 15, "label": "Encryption in transit (TLS)"},
    {"key": "rdp_remote",  "weight": 10, "label": "No exposed RDP / remote access"},
    {"key": "breach",      "weight": 10, "label": "No breach / stealer exposure"},
    {"key": "patch",       "weight": 10, "label": "Patch currency (no known CVEs)"},
    {"key": "open_ports",  "weight":  5, "label": "Minimal open port exposure"},
    {"key": "no_cleartext","weight":  5, "label": "No cleartext HTTP services"},
]


def _check_mfa(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        layer = (f.get("layer") or "").lower()
        title = (f.get("title") or "").lower()
        sev = (f.get("severity") or "").lower()
        if layer == "mfa_detection" and "no mfa" in title and sev in ("critical", "high"):
            return False, "Login portals found without MFA — enable MFA on all portals"
    return True, "MFA detected or no exposed login portals"


def _check_spf(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        if (f.get("title") or "").lower().startswith("spf"):
            sev = (f.get("severity") or "").lower()
            if sev in ("critical", "high", "medium"):
                return False, "SPF record missing or weak — publish strict SPF with -all"
    return True, "SPF policy is adequate"


def _check_dkim(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        if "dkim" in (f.get("title") or "").lower():
            sev = (f.get("severity") or "").lower()
            if sev in ("critical", "high", "medium"):
                return False, "No DKIM key found — configure DKIM signing with your email provider"
    return True, "DKIM signing detected"


def _check_dmarc(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        if "dmarc" in (f.get("title") or "").lower():
            sev = (f.get("severity") or "").lower()
            if sev in ("critical", "high"):
                return False, "DMARC missing or p=none — set DMARC to quarantine or reject"
            if sev == "medium":
                return False, "DMARC is monitoring only (p=none) — move to quarantine or reject"
    return True, "DMARC policy enforced"


def _check_encryption(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        cat = (f.get("category") or "").lower()
        title = (f.get("title") or "").lower()
        sev = (f.get("severity") or "").lower()
        if ("ssl" in cat or "tls" in cat or "ssl" in title or "tls" in title):
            if sev in ("critical", "high"):
                return False, "TLS misconfigured or using weak protocols — upgrade to TLS 1.2+"
    return True, "TLS configuration is adequate"


def _check_rdp_remote(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        detail = (f.get("technical_detail") or "").lower()
        title = (f.get("title") or "").lower()
        desc = (f.get("description") or "").lower()
        blob = f"{detail} {title} {desc}"
        if any(kw in blob for kw in (":3389", "rdp", "remote desktop", "vnc", ":5900", "teamviewer")):
            return False, "RDP or remote access port exposed — restrict to VPN or disable"
    return True, "No exposed RDP or remote access detected"


def _check_breach(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        layer = (f.get("layer") or "").lower()
        sev = (f.get("severity") or "").lower()
        if layer == "breach_monitoring" and sev in ("critical", "high"):
            return False, "Active breach or stealer data found — initiate incident response"
    return True, "No critical breach exposure detected"


def _check_patch(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        layer = (f.get("layer") or "").lower()
        cat = (f.get("category") or "").lower()
        sev = (f.get("severity") or "").lower()
        if (layer in ("nvd_supply_chain", "vertical_fingerprint") or "supply chain" in cat or "cve" in (f.get("title") or "").lower()):
            if sev in ("critical", "high"):
                return False, "Unpatched software with known CVEs — update to patched versions"
    return True, "No critical unpatched vulnerabilities detected"


def _check_open_ports(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        layer = (f.get("layer") or "").lower()
        cat = (f.get("category") or "").lower()
        if layer in ("naabu", "internetdb") and "exposure" in cat.lower():
            sev = (f.get("severity") or "").lower()
            if sev in ("critical", "high", "medium"):
                return False, "Excessive open ports — close unnecessary services"
    return True, "Port exposure within acceptable range"


def _check_no_cleartext(findings: list[dict[str, Any]]) -> tuple[bool, str]:
    for f in findings:
        title = (f.get("title") or "").lower()
        if "cleartext" in title or "http still" in title:
            return False, "Cleartext HTTP services detected — redirect all traffic to HTTPS"
    return True, "All detected services use encrypted transport"


_CHECK_FNS = {
    "mfa": _check_mfa,
    "spf": _check_spf,
    "dkim": _check_dkim,
    "dmarc": _check_dmarc,
    "encryption": _check_encryption,
    "rdp_remote": _check_rdp_remote,
    "breach": _check_breach,
    "patch": _check_patch,
    "open_ports": _check_open_ports,
    "no_cleartext": _check_no_cleartext,
}


def compute_insurance_readiness(
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the insurance readiness score and per-control breakdown."""
    controls_result: list[dict[str, Any]] = []
    earned = 0
    total_weight = 0
    improvements: list[str] = []

    for ctrl in _CONTROLS:
        key = ctrl["key"]
        weight = ctrl["weight"]
        total_weight += weight
        check_fn = _CHECK_FNS.get(key)
        if not check_fn:
            passed, note = True, "Check not implemented"
        else:
            passed, note = check_fn(findings)
        if passed:
            earned += weight
        else:
            improvements.append(f"[+{weight}%] {note}")
        controls_result.append({
            "control": ctrl["label"],
            "weight": weight,
            "passed": passed,
            "detail": note,
        })

    pct = int(round(100.0 * earned / total_weight)) if total_weight else 0

    if pct >= 85:
        tier = "Strong"
        summary = "Your organization meets most underwriter requirements. Minor improvements possible."
    elif pct >= 65:
        tier = "Moderate"
        summary = "Some controls need attention before applying for or renewing cyber insurance."
    elif pct >= 40:
        tier = "Weak"
        summary = "Significant gaps exist that will likely result in higher premiums or coverage denial."
    else:
        tier = "Poor"
        summary = "Critical security controls are missing. Insurability is at serious risk."

    return {
        "readiness_pct": pct,
        "tier": tier,
        "summary": summary,
        "controls": controls_result,
        "improvements": improvements,
    }
