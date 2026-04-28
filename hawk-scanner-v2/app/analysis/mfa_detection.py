"""MFA Detection on Exposed Login Portals.

Applies heuristics to httpx JSONL rows that look like login/auth pages.
Checks for indicators of MFA enforcement (TOTP, Duo, Auth0, Okta, etc.).
If no MFA indicator is found on a login portal, that's a critical finding.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

# Paths that indicate a login / auth surface
_LOGIN_HINTS: tuple[str, ...] = (
    "login", "signin", "sign-in", "auth", "sso",
    "admin", "wp-admin", "wp-login",
    "dashboard", "portal", "webmail", "cpanel",
    "oauth", "saml",
)

# Positive MFA indicators in response body, headers, or redirect chains
_MFA_INDICATORS: list[re.Pattern[str]] = [
    re.compile(r"totp", re.I),
    re.compile(r"two.factor", re.I),
    re.compile(r"2fa", re.I),
    re.compile(r"mfa", re.I),
    re.compile(r"multi.factor", re.I),
    re.compile(r"one.time.password", re.I),
    re.compile(r"one.time.code", re.I),
    re.compile(r"authenticator.app", re.I),
    re.compile(r"verification.code", re.I),
    re.compile(r"security.code", re.I),
    # Duo Security
    re.compile(r"duo\.com", re.I),
    re.compile(r"duosecurity", re.I),
    re.compile(r"duo-frame", re.I),
    re.compile(r"duo_iframe", re.I),
    re.compile(r"Duo-Integration", re.I),
    # Auth0
    re.compile(r"auth0\.com", re.I),
    re.compile(r"cdn\.auth0\.com", re.I),
    re.compile(r"auth0-lock", re.I),
    # Okta
    re.compile(r"okta\.com", re.I),
    re.compile(r"oktacdn\.com", re.I),
    re.compile(r"okta-sign-in", re.I),
    # Azure AD / Microsoft Entra
    re.compile(r"login\.microsoftonline\.com", re.I),
    re.compile(r"microsoft.*authenticator", re.I),
    # Google Workspace
    re.compile(r"accounts\.google\.com/.*challenge", re.I),
    # FIDO / WebAuthn
    re.compile(r"webauthn", re.I),
    re.compile(r"fido2?", re.I),
    re.compile(r"security.key", re.I),
    # Generic SSO with MFA step
    re.compile(r"step.up.auth", re.I),
    re.compile(r"challenge/", re.I),
]


def _is_login_url(url: str) -> bool:
    low = url.lower()
    return any(h in low for h in _LOGIN_HINTS)


def _has_mfa_signal(row: dict[str, Any]) -> bool:
    """Check all available fields in an httpx JSONL row for MFA indicators."""
    search_parts: list[str] = []
    for key in ("body_preview", "body", "title", "header", "response_header",
                "final_url", "url", "technologies", "chain"):
        v = row.get(key)
        if isinstance(v, str):
            search_parts.append(v)
        elif isinstance(v, list):
            search_parts.extend(str(x) for x in v)
        elif isinstance(v, dict):
            search_parts.append(str(v))

    blob = " ".join(search_parts)
    return any(p.search(blob) for p in _MFA_INDICATORS)


def detect_mfa_gaps(
    httpx_jsonl: list[dict[str, Any]],
    domain: str,
) -> list[dict[str, Any]]:
    """Scan httpx results for login portals and flag those without MFA indicators."""
    login_rows: list[dict[str, Any]] = []
    for row in httpx_jsonl or []:
        url = row.get("url") or row.get("final_url") or ""
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        if _is_login_url(url):
            login_rows.append(row)

    if not login_rows:
        return []

    no_mfa_urls: list[str] = []
    mfa_urls: list[str] = []
    for row in login_rows:
        url = (row.get("url") or row.get("final_url") or "").split("?")[0]
        if _has_mfa_signal(row):
            mfa_urls.append(url)
        else:
            no_mfa_urls.append(url)

    findings: list[dict[str, Any]] = []

    if no_mfa_urls:
        findings.append({
            "id": str(uuid.uuid4()),
            "severity": "critical",
            "category": "Access control",
            "title": "Login portal(s) with no MFA detected",
            "description": (
                f"{len(no_mfa_urls)} login or authentication portal(s) were found "
                "without any detectable multi-factor authentication. Under the 2026 HIPAA "
                "Security Rule, MFA is required for all access to systems containing ePHI."
            ),
            "technical_detail": str(no_mfa_urls[:20])[:4000],
            "affected_asset": domain,
            "remediation": (
                "Enable MFA (TOTP, FIDO2, or push) on every internet-facing login portal. "
                "Consider Duo, Okta, or Auth0 for rapid deployment."
            ),
            "layer": "mfa_detection",
            "compliance": [
                "45 CFR §164.312(d) — Person or Entity Authentication",
                "45 CFR §164.312(a)(1) — Access Control",
                "45 CFR §164.312(a)(2)(i) — Unique User Identification",
            ],
        })

    if mfa_urls:
        findings.append({
            "id": str(uuid.uuid4()),
            "severity": "ok",
            "category": "Access control",
            "title": "MFA indicators detected on login portal(s)",
            "description": (
                f"{len(mfa_urls)} login portal(s) show indicators of multi-factor authentication "
                "(Duo, Auth0, Okta, TOTP, WebAuthn, or similar)."
            ),
            "technical_detail": str(mfa_urls[:20])[:4000],
            "affected_asset": domain,
            "remediation": "Continue enforcing MFA; periodically verify coverage across all portals.",
            "layer": "mfa_detection",
            "compliance": [
                "45 CFR §164.312(d) — Person or Entity Authentication",
            ],
        })

    return findings
