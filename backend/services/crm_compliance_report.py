"""Compliance overview PDF for client portal (WeasyPrint).

Maps HAWK scan findings to US regulatory themes (HIPAA, FTC Safeguards Rule,
ABA cyber ethics).  Not legal advice — educational summary for SMBs.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _findings_list(findings: Any) -> list[dict[str, Any]]:
    if findings is None:
        return []
    if isinstance(findings, list):
        return [x for x in findings if isinstance(x, dict)]
    if isinstance(findings, dict):
        inner = findings.get("findings")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _compliance_risk_for_finding(f: dict[str, Any]) -> tuple[str, str, str]:
    """Return (regulation_label, section_note, enforcement_note)."""
    sev = str(f.get("severity") or "").lower()
    cat = str(f.get("category") or "").lower()
    title = str(f.get("title") or "").lower()
    layer = str(f.get("layer") or "").lower()
    blob = f"{cat} {title} {layer}"

    if "breach" in blob or "pwn" in blob or "stealer" in blob or "credential" in blob:
        return (
            "HIPAA §164.312 — Technical Safeguards",
            "Compromised credentials indicate insufficient access controls; breach notification "
            "to HHS OCR and affected individuals is required within 60 days for unsecured PHI.",
            "OCR may impose civil monetary penalties ($100–$50,000+ per violation). "
            "FTC Safeguards Rule requires similar breach notification within 30 days for financial institutions.",
        )
    if "email" in blob or "dmarc" in blob or "spf" in blob or "phish" in blob or "dkim" in blob:
        return (
            "HIPAA §164.312(e) — Transmission Security",
            "Email authentication controls (SPF, DKIM, DMARC) protect data in transit and reduce "
            "phishing risk that could expose protected health information or client data.",
            "Weak email security may be cited in OCR investigations or FTC enforcement actions "
            "as evidence of inadequate technical safeguards.",
        )
    if "ssl" in blob or "tls" in blob or "certificate" in blob:
        return (
            "HIPAA §164.312(e) — Transmission Security",
            "Encryption in transit is a baseline technical safeguard when collecting or displaying "
            "sensitive information over the web.",
            "Missing TLS is a common finding in OCR audits and FTC consent decrees.",
        )
    if "lookalike" in blob or "dnstwist" in blob or "typosquat" in blob:
        return (
            "FTC Act §5 — Unfair/Deceptive Practices",
            "Lookalike domains can be used to trick individuals into disclosing personal information; "
            "brand impersonation undermines consumer trust.",
            "FTC may pursue enforcement if consumers are harmed; organizations should monitor and "
            "take down infringing domains promptly.",
        )
    if "internetdb" in blob or "shodan" in blob or "internet-wide" in blob:
        return (
            "HIPAA §164.308(a)(1) — Risk Analysis",
            "Internet-wide exposure signals (open services, CVE references) indicate attack surface "
            "that could lead to unauthorized access to systems holding sensitive data.",
            "Regular risk analysis is required; public exposure increases likelihood of OCR scrutiny.",
        )
    if "nvd" in blob or "cve" in blob or "supply" in blob:
        return (
            "FTC Safeguards Rule §314.4(c) — Safeguards",
            "Known-vulnerable components or supply-chain signals indicate delayed patching of systems "
            "that may process customer financial data or PHI.",
            "Unresolved critical vulnerabilities can support enforcement findings of inadequate safeguards.",
        )
    if "subdomain" in blob or "footprint" in blob or "subfinder" in blob:
        return (
            "HIPAA §164.308(a)(1) — Risk Analysis",
            "A broad external footprint expands paths to systems storing or transmitting sensitive data.",
            "Larger attack surfaces raise the bar for access controls, monitoring, and vendor oversight.",
        )
    if "github" in blob or "secret" in blob or "leak" in blob:
        return (
            "FTC Safeguards Rule §314.4(c) — Safeguards",
            "Secrets or credentials exposed in public repositories can lead to unauthorized access.",
            "FTC has taken enforcement action against companies that failed to protect credentials.",
        )
    if sev in ("critical", "high"):
        return (
            "HIPAA §164.312 — Technical Safeguards",
            "High-severity technical exposures may indicate that security safeguards are not "
            "reasonably strong for the data being processed.",
            "Serious incidents can trigger mandatory breach notification; OCR investigations may "
            "result in corrective action plans or civil monetary penalties.",
        )
    return (
        "General — Security Best Practices",
        "Ongoing diligence, documentation, and a clear security program support compliance "
        "across HIPAA, FTC Safeguards Rule, and state breach notification laws.",
        "All 50 US states have breach notification laws; enforcement varies by state AG office.",
    )


def _regulatory_context_html() -> str:
    """Static educational block — US regulatory landscape."""
    return """
<h2>US regulatory landscape for SMBs</h2>
<p>
US businesses that handle sensitive data are subject to multiple federal and state regulations depending on
their industry:
</p>
<ul>
<li><strong>Healthcare (dental, medical):</strong> The <strong>HIPAA Security Rule</strong> (45 CFR 164)
requires administrative, physical, and technical safeguards for protected health information (PHI).
The OCR enforces breach notification within 60 days for unsecured PHI.</li>
<li><strong>Financial services (accounting, tax):</strong> The <strong>FTC Safeguards Rule</strong>
(16 CFR 314) requires a written information security program. The May 2024 amendment added 30-day
breach notification requirements.</li>
<li><strong>Legal:</strong> <strong>ABA Formal Opinion 2024-3</strong> establishes cyber ethics duties
under Model Rules 1.1, 1.4, and 1.6 — attorneys must make reasonable efforts to prevent unauthorized
access to client information.</li>
</ul>
<p>
<strong>Breach notification:</strong> All 50 US states have data breach notification laws with varying
requirements for timing, scope, and reporting. This PDF does not determine whether any finding amounts
to a reportable breach — that requires a factual incident assessment with qualified counsel.
</p>
<h2>Enforcement landscape</h2>
<ol>
<li>HHS OCR investigates HIPAA complaints and conducts audits; penalties range from $100 to $50,000+ per violation.</li>
<li>FTC pursues enforcement under Section 5 (unfair/deceptive practices) and the Safeguards Rule; consent decrees are common.</li>
<li>State attorneys general enforce state breach notification and data protection laws independently.</li>
</ol>
<p class="smallprint">
This summary is for orientation only. For breach notification, regulatory compliance, or incident response,
obtain advice from qualified US legal counsel.
</p>
"""


def build_compliance_html(
    *,
    company_name: str,
    domain: str,
    scan: dict[str, Any] | None,
) -> str:
    findings = _findings_list(scan.get("findings") if scan else None)
    score = scan.get("hawk_score") if scan else None
    grade = scan.get("grade") if scan else None

    parts = [
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/>",
        """<style>
body { font-family: system-ui, sans-serif; font-size: 11px; color: #111; max-width: 800px; margin: 0 auto; padding: 24px; }
h1 { font-size: 18px; }
h2 { font-size: 13px; margin-top: 18px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
.box { background: #f8f8f8; padding: 10px; margin: 10px 0; border-left: 3px solid #0a6; }
.box-warn { background: #fff8f0; padding: 10px; margin: 10px 0; border-left: 3px solid #c60; }
table { width: 100%; border-collapse: collapse; font-size: 10px; }
th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #eee; vertical-align: top; }
.footer { margin-top: 20px; font-size: 9px; color: #666; }
.smallprint { font-size: 9px; color: #444; line-height: 1.35; }
</style></head><body>""",
        "<h1>Compliance exposure overview</h1>",
        f'<p><strong>{_escape(company_name)}</strong> · {_escape(domain)}</p>',
        "<div class=\"box\">This document is an <strong>educational summary</strong> based on your latest HAWK external "
        "scan. It maps technical findings to <em>themes</em> under US regulatory frameworks (HIPAA, FTC Safeguards Rule, "
        "state breach notification laws). "
        "<strong>It is not legal advice.</strong> Consult qualified US legal counsel for compliance, "
        "breach notification, and regulatory matters.</div>",
    ]

    if scan:
        parts.append(
            f"<p><strong>Latest HAWK score:</strong> {score if score is not None else '—'} / 100 · "
            f"Grade {_escape(str(grade or '—'))}</p>"
        )
    else:
        parts.append("<p>No scan on file.</p>")

    parts.append(_regulatory_context_html())

    parts.append("<h2>Findings mapped to regulatory themes</h2>")
    parts.append(
        "<p class=\"smallprint\">The table links each finding to illustrative regulatory themes and enforcement risk "
        "context. Severity reflects HAWK's technical rating, not a regulatory determination.</p>"
    )
    parts.append(
        "<table><thead><tr><th>Finding</th><th>Severity</th><th>Regulation</th>"
        "<th>Section / note</th><th>Enforcement note</th></tr></thead><tbody>"
    )
    crit_high = sum(1 for x in findings if str(x.get("severity") or "").lower() in ("critical", "high"))
    fine_exposure = (
        "Low — no critical/high items in this export."
        if crit_high == 0
        else f"Elevated — {crit_high} critical/high item(s) in this export; prioritize remediation and document decisions."
    )
    for f in findings[:40]:
        regulation, section, enforcement = _compliance_risk_for_finding(f)
        parts.append(
            "<tr>"
            f"<td>{_escape(str(f.get('title', '')))}</td>"
            f"<td>{_escape(str(f.get('severity', '')))}</td>"
            f"<td>{_escape(regulation)}</td>"
            f"<td>{_escape(section)}</td>"
            f"<td>{_escape(enforcement)}</td>"
            "</tr>"
        )
    if not findings:
        parts.append(
            "<tr><td colspan=\"5\"><em>No structured findings in the latest scan payload.</em></td></tr>"
        )
    parts.append("</tbody></table>")

    parts.append("<h2>Estimated regulatory exposure</h2>")
    parts.append(f"<p>{_escape(fine_exposure)}</p>")
    parts.append(
        "<div class=\"box-warn\"><strong>Note:</strong> Enforcement is typically triggered by breaches, complaints, or "
        "audits — not by scan scores. Technical risk scores help prioritize fixes; they do not replace "
        "risk assessments or legal counsel.</div>"
    )

    parts.append(
        "<h2>Remediation priorities</h2><ol>"
        "<li><strong>Technical safeguards:</strong> Resolve critical and high findings on systems that process "
        "sensitive data; document timelines and owners.</li>"
        "<li><strong>Risk analysis:</strong> Maintain a record of what sensitive data you hold, where it flows, "
        "and who is responsible (required by HIPAA and FTC Safeguards Rule).</li>"
        "<li><strong>Breach readiness:</strong> Keep a short playbook: detect, contain, assess whether notification "
        "is required under applicable federal and state laws, and preserve evidence.</li>"
        "<li><strong>Email security:</strong> Review DMARC/SPF/DKIM and email flows where sensitive data is collected "
        "from customers, patients, or clients.</li>"
        "</ol>"
    )

    parts.append(
        "<h2>What this assessment does not cover</h2>"
        "<ul class=\"smallprint\">"
        "<li>Internal networks, employee devices, or on-prem systems not visible from an external scan.</li>"
        "<li>State-specific privacy laws (e.g. CCPA, SHIELD Act) beyond general themes.</li>"
        "<li>Contractual obligations, BAAs, or vendor agreements — legal review required.</li>"
        "</ul>"
    )

    parts.append(
        '<p class="footer">HAWK Security — compliance overview generated from scan data. '
        "Figures and themes are illustrative; they are not predictions of regulatory outcomes or penalties. "
        "For official guidance see HHS.gov (HIPAA), FTC.gov (Safeguards Rule), and your state AG website.</p></body></html>"
    )
    return "\n".join(parts)


def html_to_pdf_bytes(html: str) -> bytes | None:
    try:
        from weasyprint import HTML
    except ImportError:
        logger.warning("weasyprint not installed — compliance PDF unavailable")
        return None
    buf = BytesIO()
    HTML(string=html).write_pdf(buf)
    return buf.getvalue()
