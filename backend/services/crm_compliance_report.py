"""Vertical aware US compliance overview PDF for the client portal (WeasyPrint).

Maps the latest HAWK external scan to the regulatory framework that actually
applies to the client's practice:

* dental, medical → HIPAA Security Rule (45 CFR 164) + Breach Notification Rule
* accounting, cpa, tax → FTC Safeguards Rule (16 CFR 314) + May 2024 amendment
* legal, law → ABA Formal Opinion 24-514 + Model Rules 1.1, 1.4, 1.6

Not legal advice. Educational orientation only. All copy avoids dashes.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)


FRAMEWORK_HIPAA = "hipaa"
FRAMEWORK_FTC = "ftc_safeguards"
FRAMEWORK_ABA = "aba_24_514"
FRAMEWORK_GENERIC = "us_generic"


_VERTICAL_TO_FRAMEWORK: dict[str, str] = {
    "dental": FRAMEWORK_HIPAA,
    "medical": FRAMEWORK_HIPAA,
    "optometry": FRAMEWORK_HIPAA,
    "veterinary": FRAMEWORK_HIPAA,
    "healthcare": FRAMEWORK_HIPAA,
    "accounting": FRAMEWORK_FTC,
    "cpa": FRAMEWORK_FTC,
    "tax": FRAMEWORK_FTC,
    "bookkeeping": FRAMEWORK_FTC,
    "financial": FRAMEWORK_FTC,
    "legal": FRAMEWORK_ABA,
    "law": FRAMEWORK_ABA,
    "attorney": FRAMEWORK_ABA,
    "law_firm": FRAMEWORK_ABA,
}


def framework_for_vertical(vertical: str | None) -> str:
    """Return the compliance framework key for a prospect vertical string."""
    v = (vertical or "").strip().lower()
    if v in _VERTICAL_TO_FRAMEWORK:
        return _VERTICAL_TO_FRAMEWORK[v]
    return FRAMEWORK_GENERIC


def _escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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


# HIPAA mappings: finding category text -> (control section, note, enforcement note)
def _map_finding_hipaa(f: dict[str, Any]) -> tuple[str, str, str]:
    sev = str(f.get("severity") or "").lower()
    cat = str(f.get("category") or "").lower()
    title = str(f.get("title") or "").lower()
    layer = str(f.get("layer") or "").lower()
    blob = f"{cat} {title} {layer}"

    if any(
        k in blob for k in ("breach", "pwn", "stealer", "credential", "leak", "secret")
    ):
        return (
            "45 CFR 164.308(a)(6) and 164.404",
            "Credentials or secrets exposed externally implicate the Security Incident Procedures and the "
            "Breach Notification Rule. PHI potentially accessible through a compromised account triggers a "
            "60 day notification clock to HHS and affected individuals.",
            "HHS Office for Civil Rights publishes enforcement actions on the HHS breach portal and has issued "
            "settlements above $350K against small practices in 2024 and 2025 for failures in access management "
            "and risk analysis.",
        )
    if any(k in blob for k in ("ssl", "tls", "certificate", "hsts", "https")):
        return (
            "45 CFR 164.312(e)(1) Transmission Security",
            "Electronic protected health information transmitted over the web requires integrity and encryption "
            "controls. Weak TLS configuration or missing HSTS is directly addressable under the technical "
            "safeguards standard.",
            "OCR consistently cites Transmission Security in audit findings alongside access controls. "
            "Remediation is inexpensive; documented delay is treated as aggravating.",
        )
    if any(k in blob for k in ("dmarc", "spf", "dkim", "email", "phish")):
        return (
            "45 CFR 164.308(a)(5) Security Awareness and Training",
            "Email authentication (SPF, DKIM, DMARC) reduces phishing and impersonation risk against staff who "
            "handle PHI. HHS explicitly cites phishing as the leading cause of reported breaches since 2022.",
            "Phishing driven incidents have produced the largest HIPAA settlements of 2024. Baseline email "
            "authentication is a low cost, well documented control.",
        )
    if any(k in blob for k in ("header", "csp", "x-frame", "clickjack")):
        return (
            "45 CFR 164.308(a)(1)(ii)(B) Risk Management",
            "Missing web security headers expose web facing systems that may display or collect PHI to "
            "clickjacking and injection risks. Addressable under the Risk Management implementation "
            "specification of the Security Management Process standard.",
            "Not typically a standalone enforcement driver but a frequent audit comment when combined with "
            "other technical gaps.",
        )
    if any(k in blob for k in ("internetdb", "shodan", "port", "cve", "nvd")):
        return (
            "45 CFR 164.308(a)(1)(ii)(A) Risk Analysis",
            "Internet wide exposure of services or references to known CVEs on systems that store or process "
            "PHI is a direct input to the required Risk Analysis implementation specification.",
            "The 2023 updated HHS guidance explicitly requires Risk Analysis to consider external exposure. "
            "Failure to conduct an accurate and thorough assessment is cited in most large settlements.",
        )
    if any(
        k in blob
        for k in ("subdomain", "footprint", "typosquat", "lookalike", "dnstwist")
    ):
        return (
            "45 CFR 164.308(a)(1)(ii)(D) Information System Activity Review",
            "Uncatalogued subdomains and lookalike domains expand the surface that must be monitored for "
            "anomalous access to systems handling PHI.",
            "Relevant in post incident reviews when attackers pivot through assets not tracked by the practice.",
        )
    if sev in ("critical", "high"):
        return (
            "45 CFR 164.312 Technical Safeguards",
            "High severity external exposure suggests that one or more required or addressable technical "
            "safeguards are weak in the circumstances.",
            "OCR evaluates whether safeguards were reasonable and appropriate given the size, resources, and "
            "technical capabilities of the covered entity.",
        )
    return (
        "45 CFR 164.316 Policies and Procedures",
        "Ongoing documentation, review, and updates to policies and procedures support the Documentation "
        "standard and the Administrative Safeguards more broadly.",
        "Low severity findings rarely drive enforcement alone but are a common input to Risk Analysis.",
    )


def _map_finding_ftc(f: dict[str, Any]) -> tuple[str, str, str]:
    sev = str(f.get("severity") or "").lower()
    cat = str(f.get("category") or "").lower()
    title = str(f.get("title") or "").lower()
    layer = str(f.get("layer") or "").lower()
    blob = f"{cat} {title} {layer}"

    if any(
        k in blob for k in ("breach", "pwn", "stealer", "credential", "leak", "secret")
    ):
        return (
            "16 CFR 314.5 Breach Notification (May 2024)",
            "Exposed credentials or secrets that could allow unauthorized access to customer information "
            "implicate the 30 day breach notification requirement for incidents affecting 500 or more consumers.",
            "The May 2024 amendment added an affirmative 30 day reporting duty to the FTC. First enforcement "
            "cycle is active; FTC has signalled it will prioritize CPA and tax preparer reporting in 2025.",
        )
    if any(k in blob for k in ("ssl", "tls", "certificate", "hsts", "https")):
        return (
            "16 CFR 314.4(c)(3) Encryption",
            "Customer information transmitted over external networks must be encrypted. Weak TLS, expired "
            "certificates, or missing HTTPS redirects violate the Encryption element of a qualified Information "
            "Security Program.",
            "The 2021 final rule made encryption in transit and at rest a required program element. Documented "
            "exceptions must be approved in writing by the Qualified Individual.",
        )
    if any(k in blob for k in ("dmarc", "spf", "dkim", "email", "phish")):
        return (
            "16 CFR 314.4(d) Continuous Monitoring and Training",
            "Email authentication reduces impersonation risk against staff with access to customer financial "
            "records. Required under the Training element and supports Continuous Monitoring controls.",
            "Wire fraud via impersonated email is the single most common FTC Safeguards complaint in 2024 for "
            "CPA and tax firms.",
        )
    if any(k in blob for k in ("header", "csp", "x-frame", "clickjack")):
        return (
            "16 CFR 314.4(c)(1) Access Controls",
            "Web security headers on customer portals and tax upload portals support Access Controls and "
            "prevent session hijacking of authenticated sessions.",
            "Typically a component finding in a broader Access Control deficiency rather than a standalone "
            "enforcement target.",
        )
    if any(k in blob for k in ("internetdb", "shodan", "port", "cve", "nvd")):
        return (
            "16 CFR 314.4(b) Risk Assessment",
            "Internet wide exposure of services or references to known CVEs must be identified and treated as "
            "part of the written Risk Assessment, reviewed at least annually.",
            "The Qualified Individual must report to the Board (or equivalent) at least annually on the Risk "
            "Assessment. Unresolved high severity external exposure is a reportable material finding.",
        )
    if any(
        k in blob
        for k in ("subdomain", "footprint", "typosquat", "lookalike", "dnstwist")
    ):
        return (
            "16 CFR 314.4(d)(2) Continuous Monitoring",
            "Lookalike domains and uncatalogued subdomains expand the environment in scope for Continuous "
            "Monitoring or periodic penetration testing.",
            "Relevant to firm reputation and to wire fraud post incident analysis.",
        )
    if sev in ("critical", "high"):
        return (
            "16 CFR 314.4 Elements of an Information Security Program",
            "High severity external exposure suggests gaps in one or more of the nine required program "
            "elements.",
            "FTC examines whether program elements are appropriate to the size and complexity of the firm and "
            "the sensitivity of customer information handled.",
        )
    return (
        "16 CFR 314.4(f) Service Provider Oversight",
        "Baseline findings feed into due diligence on service providers and ongoing monitoring of their "
        "safeguards.",
        "Low severity findings rarely drive enforcement alone but are common inputs to annual reporting.",
    )


def _map_finding_aba(f: dict[str, Any]) -> tuple[str, str, str]:
    sev = str(f.get("severity") or "").lower()
    cat = str(f.get("category") or "").lower()
    title = str(f.get("title") or "").lower()
    layer = str(f.get("layer") or "").lower()
    blob = f"{cat} {title} {layer}"

    if any(
        k in blob for k in ("breach", "pwn", "stealer", "credential", "leak", "secret")
    ):
        return (
            "Model Rule 1.6(c) and Formal Opinion 24-514",
            "Exposed credentials that could allow unauthorized access to client confidential information "
            "implicate the duty of reasonable efforts to prevent inadvertent or unauthorized disclosure, and "
            "the duty to notify current clients of a material data incident affecting representation.",
            "Formal Opinion 24-514 (April 2024) affirms an affirmative notification duty. State bars in NY, CA, "
            "TX, and FL have issued parallel guidance.",
        )
    if any(k in blob for k in ("ssl", "tls", "certificate", "hsts", "https")):
        return (
            "Model Rule 1.6(c) and Comment 8 to Rule 1.1",
            "Client matter portals, document exchanges, and firm websites that transmit confidential "
            "information must use current encryption in transit. Weak TLS or missing HTTPS is inconsistent "
            "with the duty of technology competence.",
            "Reasonable efforts is judged against what is available and practical; TLS hardening is both.",
        )
    if any(k in blob for k in ("dmarc", "spf", "dkim", "email", "phish")):
        return (
            "Model Rule 1.6(c) and Rule 1.15 (Trust Accounts)",
            "Email authentication is the single largest control against wire fraud diversion of client trust "
            "funds, which is a recurring disciplinary matter for small firms.",
            "State bar disciplinary authorities treat trust account losses from phishing as direct violations "
            "of Rule 1.15 safekeeping duties.",
        )
    if any(k in blob for k in ("header", "csp", "x-frame", "clickjack")):
        return (
            "Model Rule 1.6(c)",
            "Web security headers on firm and matter portals are part of reasonable efforts against session "
            "theft and injection attacks.",
            "Typically a component finding in a broader matter portal deficiency.",
        )
    if any(k in blob for k in ("internetdb", "shodan", "port", "cve", "nvd")):
        return (
            "Comment 8 to Model Rule 1.1 and Rule 1.6(c)",
            "Known vulnerable services or CVEs on systems that store client matter data are inconsistent with "
            "the duty of technology competence and reasonable efforts.",
            "Formal Opinion 24-514 emphasizes that competence includes understanding the technology used to "
            "store and transmit client confidences.",
        )
    if any(
        k in blob
        for k in ("subdomain", "footprint", "typosquat", "lookalike", "dnstwist")
    ):
        return (
            "Model Rule 1.4 Communication",
            "Lookalike domains used to impersonate the firm expose clients to wire fraud and implicate the "
            "duty to keep clients reasonably informed about the means by which a representation is carried "
            "out.",
            "A recurring fact pattern in post incident matters where attackers impersonate firm billing.",
        )
    if sev in ("critical", "high"):
        return (
            "Model Rules 1.1, 1.4, and 1.6",
            "High severity external exposure suggests that reasonable efforts and technology competence "
            "obligations are not being met in the circumstances.",
            "Formal Opinion 24-514 frames this as an ongoing duty, not a one time assessment.",
        )
    return (
        "Model Rule 1.6(c)",
        "Baseline findings support the ongoing duty of reasonable efforts to protect client confidential "
        "information and inform firm wide policies.",
        "Low severity findings rarely drive discipline alone but are inputs to firm risk review.",
    )


_FRAMEWORK_META: dict[str, dict[str, str]] = {
    FRAMEWORK_HIPAA: {
        "title": "HIPAA external exposure overview",
        "subtitle": "HIPAA Security Rule and Breach Notification Rule",
        "citation": "45 CFR 164 Subparts C and D",
        "authority": "US Department of Health and Human Services, Office for Civil Rights (OCR)",
        "intro": (
            "The HIPAA Security Rule at 45 CFR 164 Subpart C requires covered entities and business "
            "associates to maintain reasonable and appropriate administrative, physical, and technical "
            "safeguards for electronic protected health information. The Breach Notification Rule at "
            "Subpart D requires notification to HHS and affected individuals within 60 days of discovery "
            "of a breach of unsecured PHI, and media notice for breaches affecting 500 or more individuals "
            "in a state or jurisdiction."
        ),
        "breach_clock": "60 days from discovery to HHS and affected individuals",
        "breach_notes": (
            "HHS maintains a public portal of breaches affecting 500 or more individuals. OCR has issued "
            "settlements above $350K against small practices in 2024 and 2025 for failures in access "
            "management, risk analysis, and transmission security."
        ),
        "remediation_heading": "Remediation priorities aligned to HIPAA Technical Safeguards",
        "priorities": [
            (
                "Resolve critical and high findings on any system that stores, processes, or transmits PHI. "
                "Document the risk decision and timeline."
            ),
            (
                "Keep an accurate and thorough Risk Analysis current. External exposure findings belong in "
                "the inventory of foreseeable threats."
            ),
            (
                "Maintain incident response procedures that can meet the 60 day breach notification clock, "
                "including a clear decision tree for reportability."
            ),
            (
                "Review Transmission Security on every web facing system that collects, displays, or "
                "transmits PHI. TLS hardening and HSTS are inexpensive and well documented."
            ),
        ],
        "out_of_scope": [
            "Business Associate Agreements, workforce training, and physical safeguards.",
            "Internal networks, endpoints, and on premises systems not visible from an external scan.",
            "State laws such as Washington My Health My Data, Texas HB 300, or California CMIA.",
            "Clinical workflow or electronic health record vendor configurations.",
        ],
        "footer_authority": "Office for Civil Rights, hhs.gov/ocr",
        "finding_principle_header": "HIPAA control",
        "finding_section_header": "Section and note",
        "finding_enforcement_header": "Enforcement note",
    },
    FRAMEWORK_FTC: {
        "title": "FTC Safeguards Rule external exposure overview",
        "subtitle": "Standards for Safeguarding Customer Information",
        "citation": "16 CFR 314, as amended May 2024",
        "authority": "US Federal Trade Commission, Division of Privacy and Identity Protection",
        "intro": (
            "The FTC Safeguards Rule at 16 CFR 314 requires covered financial institutions, which include "
            "tax preparers, CPA firms, and bookkeeping firms, to develop, implement, and maintain a written "
            "Information Security Program with nine required elements. The May 2024 amendment adds an "
            "affirmative requirement at 16 CFR 314.5 to notify the FTC within 30 days of discovering a "
            "notification event affecting 500 or more consumers."
        ),
        "breach_clock": "30 days from discovery to the FTC for events affecting 500 or more consumers",
        "breach_notes": (
            "The FTC has signalled that CPA and tax preparer reporting is a 2025 enforcement priority. "
            "Wire fraud from phishing is the single most common underlying incident pattern."
        ),
        "remediation_heading": "Remediation priorities aligned to the Safeguards Rule",
        "priorities": [
            (
                "Document the Qualified Individual, the written Risk Assessment, and the written Information "
                "Security Program. Review at least annually."
            ),
            (
                "Close all critical and high external exposures on systems that handle customer information. "
                "Encryption in transit and at rest is a required element."
            ),
            (
                "Operationalize Continuous Monitoring or annual penetration testing plus semi annual "
                "vulnerability assessments."
            ),
            (
                "Confirm the 30 day notification playbook at 16 CFR 314.5 is documented and rehearsed with "
                "counsel and the firm's IT provider."
            ),
        ],
        "out_of_scope": [
            "Service provider due diligence, workforce training, and access control reviews.",
            "Internal networks, endpoints, and on premises systems not visible from an external scan.",
            "State financial privacy laws that may impose additional duties.",
            "IRS Publication 4557 procedural requirements beyond what overlaps with the Safeguards Rule.",
        ],
        "footer_authority": "Federal Trade Commission, ftc.gov/business-guidance",
        "finding_principle_header": "Safeguards element",
        "finding_section_header": "Section and note",
        "finding_enforcement_header": "Enforcement note",
    },
    FRAMEWORK_ABA: {
        "title": "ABA Formal Opinion 24-514 external exposure overview",
        "subtitle": "Duty to notify clients of material data incidents",
        "citation": "ABA Formal Opinion 24-514 (April 2024) and Model Rules 1.1, 1.4, 1.6",
        "authority": "American Bar Association Standing Committee on Ethics and Professional Responsibility",
        "intro": (
            "Formal Opinion 24-514 confirms that lawyers have an affirmative duty to notify current clients "
            "of a material data incident affecting representation, grounded in Model Rules 1.1 (competence, "
            "including Comment 8 on technology competence), 1.4 (communication), and 1.6(c) (reasonable "
            "efforts to prevent inadvertent or unauthorized disclosure of client confidences). State bars in "
            "New York, California, Texas, and Florida have issued parallel guidance, and Rule 1.15 treats "
            "trust account losses from phishing as direct safekeeping violations."
        ),
        "breach_clock": "Promptly and in a manner sufficient to permit clients to make informed decisions",
        "breach_notes": (
            "The Opinion frames notification as a continuing obligation tied to the specific matter and "
            "affected client, not a fixed statutory deadline. Firms should coordinate with ethics counsel "
            "and any applicable state bar."
        ),
        "remediation_heading": "Remediation priorities aligned to Model Rules 1.1, 1.4, and 1.6",
        "priorities": [
            (
                "Resolve critical and high external exposures on any matter portal, firm website, or email "
                "system that transmits client confidential information."
            ),
            (
                "Document the firm's reasonable efforts under Rule 1.6(c). Vendor lists, monitoring posture, "
                "and incident procedures belong in a written record."
            ),
            (
                "Confirm wire instructions and trust account flows are protected by email authentication and "
                "out of band verification. Rule 1.15 losses are treated seriously by disciplinary authorities."
            ),
            (
                "Prepare a client notification template and a decision tree that ties Formal Opinion 24-514 "
                "to the matters most likely to be affected by a given incident."
            ),
        ],
        "out_of_scope": [
            "Matter specific conflicts and privilege questions that require firm counsel.",
            "Internal networks, endpoints, and on premises systems not visible from an external scan.",
            "State bar specific guidance that may impose additional duties.",
            "Client engagement letter and outside counsel guideline language.",
        ],
        "footer_authority": "American Bar Association, americanbar.org",
        "finding_principle_header": "Rule or duty",
        "finding_section_header": "Section and note",
        "finding_enforcement_header": "Discipline note",
    },
    FRAMEWORK_GENERIC: {
        "title": "US compliance external exposure overview",
        "subtitle": "State breach notification laws and cyber insurance baseline",
        "citation": "Varies by state; every US state has a data breach notification law",
        "authority": "State attorneys general and cyber insurance underwriters",
        "intro": (
            "Every US state has its own data breach notification law with varying timelines (typically 30 "
            "to 90 days) and thresholds. Cyber insurance carriers now require multi factor authentication, "
            "endpoint detection and response, and a written information security program at renewal. Your "
            "applicable regulator depends on the services you provide and the personal information you "
            "handle."
        ),
        "breach_clock": "30 to 90 days depending on state law; consult counsel for specifics",
        "breach_notes": (
            "State attorneys general have increased enforcement of existing breach laws, particularly in "
            "California, New York, Texas, and Florida. Documented delay is treated as aggravating."
        ),
        "remediation_heading": "Remediation priorities",
        "priorities": [
            "Resolve critical and high findings on any system that handles personal information.",
            "Maintain a written information security program proportionate to the sensitivity of the data.",
            "Document incident response procedures that can meet the shortest applicable state deadline.",
            "Review breach notification readiness at least annually with counsel.",
        ],
        "out_of_scope": [
            "Sector specific rules that may apply above this baseline.",
            "Internal networks, endpoints, and on premises systems not visible from an external scan.",
            "Service provider due diligence and vendor oversight.",
            "Contractual notification duties to enterprise customers.",
        ],
        "footer_authority": "Applicable state attorney general",
        "finding_principle_header": "Applicable duty",
        "finding_section_header": "Section and note",
        "finding_enforcement_header": "Enforcement note",
    },
}


def _mapper_for(framework: str):
    if framework == FRAMEWORK_HIPAA:
        return _map_finding_hipaa
    if framework == FRAMEWORK_FTC:
        return _map_finding_ftc
    if framework == FRAMEWORK_ABA:
        return _map_finding_aba
    # Generic uses HIPAA mapper tone but with neutral output via framework meta
    return _map_finding_hipaa


def build_compliance_html(
    *,
    company_name: str,
    domain: str,
    scan: dict[str, Any] | None,
    vertical: str | None,
) -> str:
    """Render the full HTML for a vertical aware US compliance overview."""
    framework = framework_for_vertical(vertical)
    meta = _FRAMEWORK_META[framework]
    mapper = _mapper_for(framework)

    findings = _findings_list(scan.get("findings") if scan else None)
    score = scan.get("hawk_score") if scan else None
    grade = scan.get("grade") if scan else None
    crit_high = sum(
        1
        for x in findings
        if str(x.get("severity") or "").lower() in ("critical", "high")
    )
    exposure_summary = (
        "Low. No critical or high severity findings in the latest scan."
        if crit_high == 0
        else (
            f"Elevated. {crit_high} critical or high severity finding(s) in the latest scan. "
            "Prioritize remediation and document the decision record."
        )
    )

    parts: list[str] = [
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>',
        """<style>
body { font-family: system-ui, sans-serif; font-size: 11px; color: #111; max-width: 800px; margin: 0 auto; padding: 24px; }
h1 { font-size: 20px; margin: 0 0 4px 0; color: #0f172a; }
h2 { font-size: 13px; margin-top: 20px; margin-bottom: 6px; color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; letter-spacing: 0.01em; }
.sub { color: #475569; font-size: 11px; margin: 0 0 12px 0; }
.meta { color: #475569; font-size: 10px; }
.box { background: #f8fafc; padding: 10px 12px; margin: 10px 0; border-left: 3px solid #0f172a; border-radius: 2px; }
.box-warn { background: #fffbeb; padding: 10px 12px; margin: 10px 0; border-left: 3px solid #b45309; border-radius: 2px; }
.box-ok { background: #f0fdf4; padding: 10px 12px; margin: 10px 0; border-left: 3px solid #15803d; border-radius: 2px; }
table { width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 6px; }
th { text-align: left; padding: 6px 6px; background: #f1f5f9; border-bottom: 1px solid #cbd5e1; color: #0f172a; font-weight: 600; }
td { text-align: left; padding: 6px 6px; border-bottom: 1px solid #e2e8f0; vertical-align: top; color: #1f2937; }
.footer { margin-top: 22px; font-size: 9px; color: #64748b; line-height: 1.5; }
.smallprint { font-size: 9px; color: #475569; line-height: 1.45; }
ol, ul { padding-left: 20px; }
li { margin-bottom: 4px; }
strong { color: #0f172a; }
</style></head><body>""",
        f"<h1>{_escape(meta['title'])}</h1>",
        f'<p class="sub">{_escape(meta["subtitle"])}. Citation: {_escape(meta["citation"])}.</p>',
        f'<p class="meta"><strong>{_escape(company_name)}</strong> &middot; {_escape(domain)}</p>',
        '<div class="box">This document is an educational summary based on your latest HAWK external scan. '
        "It maps technical findings to the framework that applies to your practice. "
        "<strong>It is not legal advice.</strong> Consult qualified US counsel for compliance, breach "
        "notification, and regulator matters.</div>",
    ]

    if scan:
        parts.append(
            f"<p><strong>Latest HAWK score:</strong> {score if score is not None else 'n/a'} out of 100, "
            f"Grade {_escape(str(grade or 'n/a'))}</p>"
        )
    else:
        parts.append(
            "<p>No scan on file yet. Run a scan to populate findings below.</p>"
        )

    parts.append(f"<h2>About this framework</h2>")
    parts.append(f"<p>{_escape(meta['intro'])}</p>")
    parts.append(
        f"<p class=\"smallprint\"><strong>Authority:</strong> {_escape(meta['authority'])}. "
        f"<strong>Breach notification:</strong> {_escape(meta['breach_clock'])}. "
        f"{_escape(meta['breach_notes'])}</p>"
    )

    parts.append("<h2>Findings mapped to this framework</h2>")
    parts.append(
        '<p class="smallprint">Severity reflects HAWK\'s technical rating. Framework sections are '
        "illustrative and do not determine regulator outcomes.</p>"
    )
    parts.append(
        f"<table><thead><tr>"
        f"<th>Finding</th><th>Severity</th>"
        f"<th>{_escape(meta['finding_principle_header'])}</th>"
        f"<th>{_escape(meta['finding_section_header'])}</th>"
        f"<th>{_escape(meta['finding_enforcement_header'])}</th>"
        f"</tr></thead><tbody>"
    )
    if not findings:
        parts.append(
            '<tr><td colspan="5"><em>No structured findings in the latest scan payload.</em></td></tr>'
        )
    else:
        for f in findings[:40]:
            principle, section, enforcement = mapper(f)
            parts.append(
                "<tr>"
                f"<td>{_escape(str(f.get('title', '')))}</td>"
                f"<td>{_escape(str(f.get('severity', '')))}</td>"
                f"<td>{_escape(principle)}</td>"
                f"<td>{_escape(section)}</td>"
                f"<td>{_escape(enforcement)}</td>"
                "</tr>"
            )
    parts.append("</tbody></table>")

    parts.append("<h2>Current exposure summary</h2>")
    if crit_high == 0:
        parts.append(f'<div class="box-ok">{_escape(exposure_summary)}</div>')
    else:
        parts.append(f'<div class="box-warn">{_escape(exposure_summary)}</div>')

    parts.append(f"<h2>{_escape(meta['remediation_heading'])}</h2><ol>")
    for p in meta["priorities"]:
        parts.append(f"<li>{_escape(p)}</li>")
    parts.append("</ol>")

    parts.append('<h2>What this overview does not cover</h2><ul class="smallprint">')
    for p in meta["out_of_scope"]:
        parts.append(f"<li>{_escape(p)}</li>")
    parts.append("</ul>")

    parts.append(
        f'<p class="footer">HAWK Security. US compliance overview generated from your latest scan data. '
        f"Framework sections and enforcement notes are illustrative. They are not predictions of regulator "
        f"outcomes, settlements, or penalties. For official guidance see {_escape(meta['footer_authority'])}. "
        "This document is not legal advice.</p></body></html>"
    )
    return "\n".join(parts)


def html_to_pdf_bytes(html: str) -> bytes | None:
    """Render HTML to PDF using WeasyPrint. Returns None if the engine is unavailable."""
    try:
        from weasyprint import HTML
    except ImportError:
        logger.warning("weasyprint not installed, compliance PDF unavailable")
        return None
    buf = BytesIO()
    HTML(string=html).write_pdf(buf)
    return buf.getvalue()
