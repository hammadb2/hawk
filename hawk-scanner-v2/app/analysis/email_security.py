"""SPF / DKIM / DMARC policy strength (dnspython)."""
from __future__ import annotations

import re
import uuid
from typing import Any

import dns.asyncresolver
import dns.exception


async def _txt_records(name: str) -> list[str]:
    try:
        answers = await dns.asyncresolver.resolve(name, "TXT", lifetime=10)
    except (dns.exception.DNSException, OSError):
        return []
    out: list[str] = []
    for rdata in answers:
        txt = rdata.to_text().strip('"')
        out.append(txt)
    return out


def _spf_strength(spf: str) -> tuple[str, str]:
    if not spf or "v=spf1" not in spf:
        return "critical", "No SPF record — spoofing risk."
    if "+all" in spf or spf.strip().endswith("all") and "?all" not in spf and "-all" not in spf and "~all" not in spf:
        return "medium", "SPF may be permissive; verify ends with -all or ~all."
    if "all" not in spf:
        return "medium", "SPF has no explicit all mechanism; review."
    if "-all" in spf:
        return "low", "SPF uses strict fail (-all) — good."
    if "~all" in spf:
        return "low", "SPF uses softfail (~all) — acceptable; consider -all."
    return "low", "SPF present; confirm includes cover all senders."


def _dmarc_strength(records: list[str]) -> tuple[str, str, str]:
    raw = ""
    for txt in records:
        if "v=DMARC1" in txt.upper() or "v=dmarc1" in txt:
            raw = txt
            break
    if not raw:
        return "high", "", "No DMARC record — phishing and spoofing harder to detect."
    m = re.search(r"p=(\w+)", raw, re.I)
    pol = (m.group(1) if m else "none").lower()
    if pol == "reject":
        return "low", raw, "DMARC policy is reject — strong."
    if pol == "quarantine":
        return "low", raw, "DMARC policy is quarantine — good; consider reject."
    if pol == "none":
        return "medium", raw, "DMARC p=none — monitoring only; increase to quarantine/reject."
    return "low", raw, "DMARC present; verify alignment and reporting."


async def analyze(domain: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    base = domain.lower().strip()

    spf_txts = await _txt_records(base)
    spf_flat = " ".join(spf_txts)
    spf_line = next((t for t in spf_txts if "v=spf1" in t), "")
    sev, note = _spf_strength(spf_line)
    findings.append(
        {
            "id": str(uuid.uuid4()),
            "severity": sev,
            "category": "Email Security",
            "title": "SPF policy",
            "description": note,
            "technical_detail": spf_line[:2000] or spf_flat[:2000],
            "affected_asset": f"TXT @{base}",
            "remediation": "Publish a correct SPF TXT and tighten to -all when all senders are known.",
            "layer": "email_security",
        }
    )

    dmarc_name = f"_dmarc.{base}"
    dmarc_txts = await _txt_records(dmarc_name)
    d_sev, d_raw, d_note = _dmarc_strength(dmarc_txts)
    findings.append(
        {
            "id": str(uuid.uuid4()),
            "severity": d_sev,
            "category": "Email Security",
            "title": "DMARC policy",
            "description": d_note,
            "technical_detail": d_raw[:2000],
            "affected_asset": f"TXT @{dmarc_name}",
            "remediation": "Add DMARC with gradual move to quarantine then reject.",
            "layer": "email_security",
        }
    )

    # DKIM: common selectors (limited pass)
    selectors = ["default", "google", "selector1", "selector2", "k1", "s1"]
    dkim_found = False
    for sel in selectors:
        name = f"{sel}._domainkey.{base}"
        txts = await _txt_records(name)
        if any("v=DKIM1" in t or "p=" in t for t in txts):
            dkim_found = True
            break
    findings.append(
        {
            "id": str(uuid.uuid4()),
            "severity": "low" if dkim_found else "medium",
            "category": "Email Security",
            "title": "DKIM selectors",
            "description": "DKIM key found for a common selector."
            if dkim_found
            else "No DKIM found for common selectors — verify provider-specific selectors.",
            "technical_detail": "Checked common selectors only; full audit requires provider docs.",
            "affected_asset": base,
            "remediation": "Enable DKIM with your mail provider and rotate keys periodically.",
            "layer": "email_security",
        }
    )

    return findings
