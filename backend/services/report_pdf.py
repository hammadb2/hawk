"""Generate HAWK scan report PDF with reportlab (pure Python, no system dependencies)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.models import Scan


def render_report_pdf(
    scan: Scan,
    sections: list[str],
    output_path: Path,
    client_name: str | None = None,
    client_company: str | None = None,
) -> bool:
    """Generate PDF at output_path using reportlab. Returns True on success."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_LEFT
    except ImportError:
        return False

    try:
        domain = scan.scanned_domain or (
            scan.domain.domain if getattr(scan, "domain", None) and scan.domain else "unknown"
        )
        score = scan.score or 0
        grade = scan.grade or "—"
        findings: list[dict[str, Any]] = []
        try:
            findings = json.loads(scan.findings_json or "[]")
        except Exception:
            pass

        critical = [f for f in findings if f.get("severity") == "critical"]
        warning = [f for f in findings if f.get("severity") == "warning"]
        info = [f for f in findings if f.get("severity") == "info"]
        ok = [f for f in findings if f.get("severity") == "ok"]

        SEV_COLORS = {
            "critical": colors.HexColor("#DC2626"),
            "warning": colors.HexColor("#EA580C"),
            "info": colors.HexColor("#2563EB"),
            "ok": colors.HexColor("#16A34A"),
        }
        GRADE_COLORS = {
            "A": colors.HexColor("#16A34A"),
            "B": colors.HexColor("#2563EB"),
            "C": colors.HexColor("#CA8A04"),
            "D": colors.HexColor("#EA580C"),
            "F": colors.HexColor("#DC2626"),
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        styles = getSampleStyleSheet()
        normal = styles["Normal"]
        story = []

        # ── Title ──────────────────────────────────────────────────────────
        title_style = ParagraphStyle("title", parent=normal, fontSize=22, fontName="Helvetica-Bold", textColor=colors.HexColor("#0F0A1E"), spaceAfter=4)
        story.append(Paragraph("HAWK Security Report", title_style))

        meta_style = ParagraphStyle("meta", parent=normal, fontSize=10, textColor=colors.HexColor("#666688"), spaceAfter=2)
        if client_name or client_company:
            prepared = f"Prepared for: <b>{client_name or ''}</b>"
            if client_company:
                prepared += f" — {client_company}"
            story.append(Paragraph(prepared, meta_style))
        story.append(Paragraph(f"Domain: <b>{domain}</b>", meta_style))
        story.append(Spacer(1, 12))

        def add_section(title: str) -> None:
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#C8C3DC"), spaceAfter=6))
            heading_style = ParagraphStyle("heading", parent=normal, fontSize=13, fontName="Helvetica-Bold", textColor=colors.HexColor("#0F0A1E"), spaceBefore=6, spaceAfter=6)
            story.append(Paragraph(title, heading_style))

        body_style = ParagraphStyle("body", parent=normal, fontSize=10, textColor=colors.HexColor("#282337"), spaceAfter=4, leading=15)

        # ── Executive Summary ──────────────────────────────────────────────
        if "executive" in sections:
            add_section("Executive Summary")
            grade_color = GRADE_COLORS.get(grade.upper()[:1], colors.grey)
            grade_style = ParagraphStyle("grade", parent=normal, fontSize=36, fontName="Helvetica-Bold", textColor=grade_color, spaceAfter=4)
            story.append(Paragraph(grade, grade_style))
            story.append(Paragraph(f"Score: {score}/100", body_style))
            story.append(Paragraph(
                f"Critical: {len(critical)} &nbsp;&nbsp; Warning: {len(warning)} &nbsp;&nbsp; Info: {len(info)} &nbsp;&nbsp; OK: {len(ok)}",
                body_style,
            ))
            story.append(Spacer(1, 12))

        # ── Findings ───────────────────────────────────────────────────────
        if "findings" in sections and findings:
            add_section("Findings")

            header_row = [
                Paragraph("<b>Severity</b>", body_style),
                Paragraph("<b>Category</b>", body_style),
                Paragraph("<b>Title</b>", body_style),
                Paragraph("<b>Remediation</b>", body_style),
            ]
            table_data = [header_row]
            col_widths = [1.0 * inch, 1.2 * inch, 2.5 * inch, 2.3 * inch]

            small_style = ParagraphStyle("small", parent=normal, fontSize=8, leading=11)

            for f in findings:
                sev = (f.get("severity") or "info").lower()
                sev_color = SEV_COLORS.get(sev, colors.grey)
                sev_para = Paragraph(
                    f'<font color="{sev_color.hexval()}"><b>{sev}</b></font>',
                    small_style,
                )
                table_data.append([
                    sev_para,
                    Paragraph(str(f.get("category", ""))[:25], small_style),
                    Paragraph(str(f.get("title", ""))[:80], small_style),
                    Paragraph(str(f.get("remediation", ""))[:120], small_style),
                ])

            tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EBE8FA")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#322850")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F5FF")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0DCF0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 12))

        # ── Compliance ─────────────────────────────────────────────────────
        if "compliance" in sections:
            add_section("Compliance")
            compliance_refs: set[str] = set()
            for f in findings:
                for c in f.get("compliance") or []:
                    compliance_refs.add(c)
            if compliance_refs:
                story.append(Paragraph(
                    "This scan surfaces findings relevant to: " + ", ".join(sorted(compliance_refs)) + ".",
                    body_style,
                ))
            else:
                story.append(Paragraph(
                    "No specific compliance references in this scan. "
                    "See your dashboard Compliance page for PIPEDA / Bill C-26 mapping.",
                    body_style,
                ))
            story.append(Spacer(1, 12))

        # ── Footer ─────────────────────────────────────────────────────────
        footer_style = ParagraphStyle("footer", parent=normal, fontSize=8, textColor=colors.HexColor("#9691AA"))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E0DCF0"), spaceBefore=12, spaceAfter=6))
        story.append(Paragraph("Generated by HAWK — hawk.akbstudios.com", footer_style))

        doc.build(story)
        return output_path.exists()

    except Exception:
        return False
