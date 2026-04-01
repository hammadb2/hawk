"""2D — PIPEDA-oriented compliance PDF for client portal (WeasyPrint)."""

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


def _pipeda_risk_for_finding(f: dict[str, Any]) -> tuple[str, str, str]:
    """Return (principle_label, section_note, fine_note)."""
    sev = str(f.get("severity") or "").lower()
    cat = str(f.get("category") or "").lower()
    title = str(f.get("title") or "").lower()
    blob = f"{cat} {title}"

    if "breach" in blob or "pwn" in blob or "stealer" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Poor safeguards increase risk of privacy breach; breach notification may be required under PIPEDA (Section 10.1).",
            "OPC can recommend compliance orders; serious cases may face Federal Court penalties.",
        )
    if "email" in blob or "dmarc" in blob or "spf" in blob or "phish" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Email authentication gaps undermine protection of personal information sent or received by the organization.",
            "Non-compliance contributes to complaint risk and reputational harm.",
        )
    if "ssl" in blob or "tls" in blob or "certificate" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Encryption in transit is a baseline safeguard for personal data handled over the web.",
            "Moderate regulatory exposure if customer/patient data is intercepted.",
        )
    if sev in ("critical", "high"):
        return (
            "Principle 4.7 — Safeguards",
            "High-severity technical exposures may indicate inadequate security safeguards for personal information.",
            "Varies by incident; serious breaches can trigger mandatory reporting and reputational costs.",
        )
    return (
        "General accountability",
        "Ongoing diligence is required under PIPEDA accountability and openness principles.",
        "Illustrative small-business incident costs often reach six figures including response and downtime.",
    )


def build_pipeda_html(
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
h2 { font-size: 13px; margin-top: 18px; border-bottom: 1px solid #ccc; }
.box { background: #f8f8f8; padding: 10px; margin: 10px 0; border-left: 3px solid #0a6; }
table { width: 100%; border-collapse: collapse; font-size: 10px; }
th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #eee; vertical-align: top; }
.footer { margin-top: 20px; font-size: 9px; color: #666; }
</style></head><body>""",
        "<h1>PIPEDA exposure overview (illustrative)</h1>",
        f'<p><strong>{_escape(company_name)}</strong> · {_escape(domain)}</p>',
        "<div class=\"box\">This document is an educational summary based on your latest HAWK scan. "
        "It is not legal advice. Consult qualified privacy counsel for PIPEDA compliance decisions.</div>",
    ]

    if scan:
        parts.append(
            f"<p><strong>Latest HAWK score:</strong> {score if score is not None else '—'} / 100 · "
            f"Grade {_escape(str(grade or '—'))}</p>"
        )
    else:
        parts.append("<p>No scan on file.</p>")

    parts.append("<h2>Findings mapped to PIPEDA themes</h2>")
    parts.append(
        "<table><thead><tr><th>Finding</th><th>Severity</th><th>PIPEDA principle</th>"
        "<th>Section / note</th><th>Risk note</th></tr></thead><tbody>"
    )
    fine_exposure = "Low — no critical items flagged." if not findings else "Elevated — address critical/high items promptly."
    for f in findings[:40]:
        principle, section, fine = _pipeda_risk_for_finding(f)
        parts.append(
            "<tr>"
            f"<td>{_escape(str(f.get('title', '')))}</td>"
            f"<td>{_escape(str(f.get('severity', '')))}</td>"
            f"<td>{_escape(principle)}</td>"
            f"<td>{_escape(section)}</td>"
            f"<td>{_escape(fine)}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")

    parts.append("<h2>Estimated regulatory / incident exposure (illustrative)</h2>")
    parts.append(f"<p>{_escape(fine_exposure)}</p>")
    parts.append(
        "<h2>Remediation priorities</h2><ol>"
        "<li>Resolve all critical and high findings within 30 days.</li>"
        "<li>Document safeguards and training (accountability principle).</li>"
        "<li>Prepare a breach notification playbook for service providers handling personal data.</li>"
        "</ol>"
    )
    parts.append(
        '<p class="footer">HAWK Security — PIPEDA overview generated from scan data. '
        "Figures are illustrative and not OPC or court estimates.</p></body></html>"
    )
    return "\n".join(parts)


def html_to_pdf_bytes(html: str) -> bytes | None:
    try:
        from weasyprint import HTML
    except ImportError:
        logger.warning("weasyprint not installed — PIPEDA PDF unavailable")
        return None
    buf = BytesIO()
    HTML(string=html).write_pdf(buf)
    return buf.getvalue()
