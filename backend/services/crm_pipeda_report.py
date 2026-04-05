"""2D — PIPEDA-oriented compliance PDF for client portal (WeasyPrint).

Phase 4 — Deeper OPC / enforcement framing: complaint pathway, safeguards, breach notification context.
Not legal advice — educational summary for SMBs.
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


def _pipeda_risk_for_finding(f: dict[str, Any]) -> tuple[str, str, str]:
    """Return (principle_label, section_note, regulatory_note)."""
    sev = str(f.get("severity") or "").lower()
    cat = str(f.get("category") or "").lower()
    title = str(f.get("title") or "").lower()
    layer = str(f.get("layer") or "").lower()
    blob = f"{cat} {title} {layer}"

    if "breach" in blob or "pwn" in blob or "stealer" in blob or "credential" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Poor safeguards increase the risk of a privacy breach affecting personal information; "
            "mandatory breach reporting to the OPC and affected individuals may apply under PIPEDA (s. 10.1) when "
            "a real risk of significant harm exists.",
            "The OPC investigates complaints; it may recommend compliance steps. Serious or repeated issues can lead "
            "to Federal Court orders. This document does not assess whether a specific incident is reportable.",
        )
    if "email" in blob or "dmarc" in blob or "spf" in blob or "phish" in blob or "dkim" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Email authentication and anti-abuse controls protect personal information in transit and reduce "
            "impersonation that could expose personal data.",
            "Weak email controls increase complaint risk if personal information is mishandled; OPC investigations "
            "often focus on whether safeguards were reasonable in the circumstances.",
        )
    if "ssl" in blob or "tls" in blob or "certificate" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Encryption in transit is a baseline safeguard when personal information is collected or displayed over the web.",
            "If interception or disclosure occurs, breach notification and OPC scrutiny may follow depending on facts.",
        )
    if "lookalike" in blob or "dnstwist" in blob or "typosquat" in blob:
        return (
            "Principle 4.3 — Consent & openness",
            "Lookalike domains can be used to trick individuals into disclosing personal information; "
            "undermines consent and openness expectations.",
            "Fraud-related complaints may involve law enforcement; OPC may still examine privacy practices if "
            "personal information is involved.",
        )
    if "internetdb" in blob or "shodan" in blob or "internet-wide" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Internet-wide exposure signals (e.g. open services, CVE references) suggest attack surface that could "
            "lead to unauthorized access to systems holding personal information.",
            "OPC looks at whether security safeguards were proportionate; public exposure increases incident likelihood.",
        )
    if "nvd" in blob or "cve" in blob or "supply" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Known-vulnerable components or supply-chain signals may indicate delayed patching of systems that "
            "process personal data.",
            "Unresolved critical/high technical debt can support an OPC finding of inadequate safeguards if a breach occurs.",
        )
    if "subdomain" in blob or "footprint" in blob or "subfinder" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "A broad external footprint can expand paths to systems that store or transmit personal information.",
            "Larger attack surfaces raise the bar for monitoring, access control, and vendor oversight.",
        )
    if "github" in blob or "secret" in blob or "leak" in blob:
        return (
            "Principle 4.7 — Safeguards",
            "Secrets or credentials exposed in public repositories can lead to unauthorized access to personal data.",
            "OPC may examine whether the organization had reasonable policies and technical controls for development.",
        )
    if sev in ("critical", "high"):
        return (
            "Principle 4.7 — Safeguards",
            "High-severity technical exposures may indicate that security safeguards for personal information are not "
            "reasonably strong in the circumstances (PIPEDA s. 10.1 context for breaches is separate).",
            "Serious incidents can trigger mandatory breach notification; OPC investigations can recommend compliance "
            "measures and, in some cases, Federal Court enforcement.",
        )
    return (
        "Principles 4.1 & 4.1.2 — Accountability",
        "Ongoing diligence, documentation, and a clear privacy management program support accountability under PIPEDA.",
        "PIPEDA is largely complaint-driven; the OPC does not impose GDPR-style administrative fines, but Federal Court "
        "orders and reputational harm from OPC findings remain material risks.",
    )


def _opc_context_html() -> str:
    """Static educational block — Office of the Privacy Commissioner of Canada (OPC)."""
    return """
<h2>How PIPEDA fits with the Office of the Privacy Commissioner (OPC)</h2>
<p>
Under Canada’s <em>Personal Information Protection and Electronic Documents Act</em> (PIPEDA), organizations that collect,
use, or disclose personal information in the course of commercial activities must follow the ten fair information
principles (Schedule 1), including <strong>accountability</strong> and <strong>safeguards</strong>.
</p>
<p>
The <strong>OPC</strong> receives individual complaints, may conduct investigations, publish findings, and seek
<strong>compliance agreements</strong> or refer matters to the <strong>Federal Court</strong> where appropriate.
PIPEDA is <strong>not</strong> structured like some foreign regimes with fixed “GDPR-style” administrative fines for
every breach; outcomes depend on facts, cooperation, and whether the Court is invoked.
</p>
<p>
<strong>Breach notification:</strong> Organizations must notify the OPC and affected individuals when a breach of
security safeguards creates a <strong>real risk of significant harm</strong> (PIPEDA s. 10.1). This PDF does not
determine whether any finding amounts to a reportable breach — that requires a factual incident assessment.
</p>
<p class="smallprint">
If you operate mainly within a province with substantially similar private-sector legislation (e.g. Alberta, B.C.,
Quebec), provincial rules may apply instead of or alongside PIPEDA. Confirm with counsel.
</p>
<h2>Complaint pathway (simplified)</h2>
<ol>
<li>An individual files a complaint with the OPC (or in some cases with the organization first).</li>
<li>The OPC may investigate, request records, and issue a report with recommendations.</li>
<li>Unresolved cases may proceed to the Federal Court for orders and, in limited circumstances, penalties under PIPEDA.</li>
</ol>
<p class="smallprint">
This summary is for orientation only. For breach notification, contracts, or cross-border transfers, obtain advice
from a qualified Canadian privacy lawyer.
</p>
"""


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
h2 { font-size: 13px; margin-top: 18px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
.box { background: #f8f8f8; padding: 10px; margin: 10px 0; border-left: 3px solid #0a6; }
.box-warn { background: #fff8f0; padding: 10px; margin: 10px 0; border-left: 3px solid #c60; }
table { width: 100%; border-collapse: collapse; font-size: 10px; }
th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #eee; vertical-align: top; }
.footer { margin-top: 20px; font-size: 9px; color: #666; }
.smallprint { font-size: 9px; color: #444; line-height: 1.35; }
</style></head><body>""",
        "<h1>PIPEDA exposure overview</h1>",
        f'<p><strong>{_escape(company_name)}</strong> · {_escape(domain)}</p>',
        "<div class=\"box\">This document is an <strong>educational summary</strong> based on your latest HAWK external "
        "scan. It maps technical findings to <em>themes</em> under PIPEDA’s fair information principles. "
        "<strong>It is not legal advice.</strong> Consult qualified Canadian privacy counsel for compliance, "
        "breach notification, and OPC or provincial regulator matters.</div>",
    ]

    if scan:
        parts.append(
            f"<p><strong>Latest HAWK score:</strong> {score if score is not None else '—'} / 100 · "
            f"Grade {_escape(str(grade or '—'))}</p>"
        )
    else:
        parts.append("<p>No scan on file.</p>")

    parts.append(_opc_context_html())

    parts.append("<h2>Findings mapped to PIPEDA themes</h2>")
    parts.append(
        "<p class=\"smallprint\">The table links each finding to illustrative PIPEDA principles and regulatory risk "
        "themes. Severity reflects HAWK’s technical rating, not an OPC or court determination.</p>"
    )
    parts.append(
        "<table><thead><tr><th>Finding</th><th>Severity</th><th>PIPEDA principle</th>"
        "<th>Section / note</th><th>OPC / incident note</th></tr></thead><tbody>"
    )
    crit_high = sum(1 for x in findings if str(x.get("severity") or "").lower() in ("critical", "high"))
    fine_exposure = (
        "Low — no critical/high items in this export."
        if crit_high == 0
        else f"Elevated — {crit_high} critical/high item(s) in this export; prioritize remediation and document decisions."
    )
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
    if not findings:
        parts.append(
            "<tr><td colspan=\"5\"><em>No structured findings in the latest scan payload.</em></td></tr>"
        )
    parts.append("</tbody></table>")

    parts.append("<h2>Estimated regulatory / incident exposure</h2>")
    parts.append(f"<p>{_escape(fine_exposure)}</p>")
    parts.append(
        "<div class=\"box-warn\"><strong>Note:</strong> PIPEDA enforcement is typically triggered by complaints or "
        "serious incidents, not by scan scores. Technical risk scores help prioritize fixes; they do not replace "
        "privacy impact assessments or legal counsel.</div>"
    )

    parts.append(
        "<h2>Remediation priorities (OPC-aligned themes)</h2><ol>"
        "<li><strong>Safeguards:</strong> Resolve critical and high findings on systems that process personal "
        "information; document timelines and owners.</li>"
        "<li><strong>Accountability:</strong> Maintain a simple record of what personal data you hold, where it flows, "
        "and who is responsible (privacy accountability principle).</li>"
        "<li><strong>Breach readiness:</strong> Keep a short playbook: detect, contain, assess whether notification "
        "to the OPC and individuals is required (s. 10.1), and preserve evidence.</li>"
        "<li><strong>Vendor / email:</strong> Review DMARC/SPF/DKIM and email flows where personal data is collected "
        "from customers or patients.</li>"
        "</ol>"
    )

    parts.append(
        "<h2>What this assessment does not cover</h2>"
        "<ul class=\"smallprint\">"
        "<li>Internal networks, employee devices, or on-prem systems not visible from an external scan.</li>"
        "<li>Provincial health information laws (e.g. HIA) or sector-specific rules beyond PIPEDA themes.</li>"
        "<li>Lawfulness of processing, consent wording, or contracts — legal review required.</li>"
        "</ul>"
    )

    parts.append(
        '<p class="footer">HAWK Security — PIPEDA overview generated from scan data. '
        "Figures and themes are illustrative; they are not predictions of OPC outcomes, fines, or court penalties. "
        "For official guidance see the Office of the Privacy Commissioner of Canada (priv.gc.ca).</p></body></html>"
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
