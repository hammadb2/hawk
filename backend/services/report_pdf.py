"""Generate HAWK scan report PDF with reportlab — branded design."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_URL
from models import Scan

# ── Brand palette ──────────────────────────────────────────────────────────────
_BG        = "#07060C"
_SURFACE   = "#0D0B14"
_SURFACE2  = "#13111E"
_ACCENT    = "#7B5CF5"
_ACCENT_LT = "#9B80FF"
_TXT       = "#F2F0FA"
_TXT_SEC   = "#9B98B4"
_TXT_DIM   = "#5C5876"
_RED       = "#F87171"
_ORANGE    = "#FB923C"
_BLUE      = "#60A5FA"
_GREEN     = "#34D399"
_YELLOW    = "#FBBF24"

_GRADE_COLOR = {"A": _GREEN, "B": _BLUE, "C": _YELLOW, "D": _ORANGE, "F": _RED}
_SEV_COLOR   = {"critical": _RED, "warning": _ORANGE, "info": _BLUE, "ok": _GREEN}
_SEV_BG      = {
    "critical": "#2D0A0A",
    "warning":  "#2D1500",
    "info":     "#0A1A2D",
    "ok":       "#0A2D1A",
}


def render_report_pdf(
    scan: Scan,
    sections: list[str],
    output_path: Path,
    client_name: str | None = None,
    client_company: str | None = None,
) -> bool:
    """Generate branded HAWK PDF at output_path. Returns True on success."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, KeepTogether,
        )
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        from reportlab.platypus.flowables import HRFlowable as HR
    except ImportError:
        return False

    try:
        # ── Scan data ──────────────────────────────────────────────────────
        domain = scan.scanned_domain or (
            scan.domain.domain if getattr(scan, "domain", None) and scan.domain else "unknown"
        )
        score: int = scan.score or 0
        grade: str = scan.grade or "?"
        findings: list[dict[str, Any]] = []
        try:
            findings = json.loads(scan.findings_json or "[]")
        except Exception:
            pass

        critical = [f for f in findings if f.get("severity") == "critical"]
        warning  = [f for f in findings if f.get("severity") == "warning"]
        info     = [f for f in findings if f.get("severity") == "info"]
        ok       = [f for f in findings if f.get("severity") == "ok"]

        now_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

        def c(hex_str: str) -> colors.HexColor:
            return colors.HexColor(hex_str)

        # ── Page setup ─────────────────────────────────────────────────────
        output_path.parent.mkdir(parents=True, exist_ok=True)
        W, H = letter  # 612 x 792 pt
        CONTENT_W = W - 1.5 * inch  # usable width inside margins

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.6 * inch,
        )

        base = getSampleStyleSheet()["Normal"]

        def sty(name: str, **kw) -> ParagraphStyle:
            return ParagraphStyle(name, parent=base, **kw)

        # ── Shared styles ──────────────────────────────────────────────────
        s_body  = sty("body",  fontSize=9,  textColor=c(_TXT_SEC), leading=14)
        s_small = sty("small", fontSize=8,  textColor=c(_TXT_SEC), leading=12)
        s_label = sty("label", fontSize=7,  textColor=c(_TXT_DIM), leading=10,
                       fontName="Helvetica-Bold", spaceAfter=1)

        story: list = []

        # ══════════════════════════════════════════════════════════════════
        # COVER HEADER — dark band
        # ══════════════════════════════════════════════════════════════════
        hawk_style  = sty("hawk",  fontSize=28, fontName="Helvetica-Bold",
                           textColor=c(_ACCENT), leading=32)
        sub_style   = sty("sub",   fontSize=11, fontName="Helvetica",
                           textColor=c(_TXT), leading=14)
        domain_style = sty("dom",  fontSize=14, fontName="Helvetica-Bold",
                           textColor=c(_TXT), leading=18)
        date_style   = sty("date", fontSize=8, textColor=c(_TXT_DIM),
                           alignment=TA_RIGHT)

        header_data = [[
            Table(
                [[Paragraph("HAWK", hawk_style)],
                 [Paragraph("Security Report", sub_style)]],
                colWidths=[CONTENT_W * 0.6],
                style=TableStyle([
                    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                    ("TOPPADDING",    (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]),
            ),
            Table(
                [[Paragraph(now_str, date_style)]],
                colWidths=[CONTENT_W * 0.4],
                style=TableStyle([
                    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                    ("TOPPADDING",    (0, 0), (-1, -1), 14),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]),
            ),
        ]]

        header_tbl = Table(
            header_data,
            colWidths=[CONTENT_W * 0.6, CONTENT_W * 0.4],
            style=TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), c(_SURFACE)),
                ("LEFTPADDING",   (0, 0), (-1, -1), 16),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
                ("TOPPADDING",    (0, 0), (-1, -1), 18),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("ROUNDEDCORNERS", [6]),
            ]),
        )
        story.append(header_tbl)
        story.append(Spacer(1, 6))

        # Domain + prepared-for row
        meta_left = domain
        if client_name or client_company:
            who = client_name or ""
            if client_company:
                who += f" · {client_company}"
            meta_left = f"{domain}   |   Prepared for {who}"

        meta_tbl = Table(
            [[Paragraph(meta_left, sty("meta_l", fontSize=9,
                        textColor=c(_TXT_SEC), fontName="Helvetica"))]],
            colWidths=[CONTENT_W],
            style=TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), c(_SURFACE2)),
                ("LEFTPADDING",   (0, 0), (-1, -1), 16),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
                ("TOPPADDING",    (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ROUNDEDCORNERS", [4]),
            ]),
        )
        story.append(meta_tbl)
        story.append(Spacer(1, 14))

        # ══════════════════════════════════════════════════════════════════
        # EXECUTIVE SUMMARY
        # ══════════════════════════════════════════════════════════════════
        if "executive" in sections:
            # Section title
            story.append(Paragraph(
                "EXECUTIVE SUMMARY",
                sty("sec_hd", fontSize=7, fontName="Helvetica-Bold",
                    textColor=c(_ACCENT), spaceAfter=6, tracking=1),
            ))

            grade_col   = c(_GRADE_COLOR.get(grade.upper()[:1], _TXT_DIM))
            score_pct   = max(0, min(100, score))

            # Grade + score block
            grade_inner = Table(
                [[
                    Paragraph(
                        grade,
                        sty("grd", fontSize=52, fontName="Helvetica-Bold",
                            textColor=grade_col, leading=56, alignment=TA_CENTER),
                    ),
                    Table(
                        [
                            [Paragraph("SCORE", s_label)],
                            [Paragraph(f"{score_pct}/100",
                                       sty("sc_val", fontSize=22, fontName="Helvetica-Bold",
                                           textColor=c(_TXT), leading=26))],
                            [Spacer(1, 4)],
                            # score bar
                            [Table(
                                [[
                                    Table([[""]], colWidths=[CONTENT_W * 0.35 * score_pct / 100],
                                          style=TableStyle([
                                              ("BACKGROUND", (0,0),(-1,-1), grade_col),
                                              ("TOPPADDING",(0,0),(-1,-1),4),
                                              ("BOTTOMPADDING",(0,0),(-1,-1),4),
                                          ])),
                                ]],
                                colWidths=[CONTENT_W * 0.35],
                                style=TableStyle([
                                    ("BACKGROUND", (0,0),(-1,-1), c(_SURFACE2)),
                                    ("TOPPADDING",(0,0),(-1,-1),0),
                                    ("BOTTOMPADDING",(0,0),(-1,-1),0),
                                    ("LEFTPADDING",(0,0),(-1,-1),0),
                                    ("RIGHTPADDING",(0,0),(-1,-1),0),
                                    ("ROUNDEDCORNERS", [3]),
                                ]),
                            )],
                        ],
                        colWidths=[CONTENT_W * 0.45],
                        style=TableStyle([
                            ("LEFTPADDING",   (0,0),(-1,-1), 0),
                            ("RIGHTPADDING",  (0,0),(-1,-1), 0),
                            ("TOPPADDING",    (0,0),(-1,-1), 2),
                            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
                            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                        ]),
                    ),
                ]],
                colWidths=[CONTENT_W * 0.15, CONTENT_W * 0.45],
                style=TableStyle([
                    ("LEFTPADDING",   (0,0),(-1,-1), 0),
                    ("RIGHTPADDING",  (0,0),(-1,-1), 20),
                    ("TOPPADDING",    (0,0),(-1,-1), 0),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                ]),
            )

            # Stat badges: Critical / Warning / Info / OK
            stat_items = [
                ("CRITICAL", len(critical), _RED),
                ("WARNING",  len(warning),  _ORANGE),
                ("INFO",     len(info),     _BLUE),
                ("OK",       len(ok),       _GREEN),
            ]
            badge_w = CONTENT_W / 4

            badge_row = []
            for label, count, color in stat_items:
                badge_row.append(Table(
                    [
                        [Paragraph(str(count),
                                   sty(f"bc_{label}", fontSize=20, fontName="Helvetica-Bold",
                                       textColor=c(color), alignment=TA_CENTER, leading=24))],
                        [Paragraph(label,
                                   sty(f"bl_{label}", fontSize=6, fontName="Helvetica-Bold",
                                       textColor=c(color), alignment=TA_CENTER, leading=9))],
                    ],
                    colWidths=[badge_w - 8],
                    style=TableStyle([
                        ("BACKGROUND",    (0,0),(-1,-1), c(_SURFACE2)),
                        ("LEFTPADDING",   (0,0),(-1,-1), 6),
                        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
                        ("TOPPADDING",    (0,0),(-1,-1), 10),
                        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
                        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
                        ("ROUNDEDCORNERS", [5]),
                    ]),
                ))

            badges_tbl = Table(
                [badge_row],
                colWidths=[badge_w] * 4,
                style=TableStyle([
                    ("LEFTPADDING",   (0,0),(-1,-1), 0),
                    ("RIGHTPADDING",  (0,0),(-1,-1), 8),
                    ("TOPPADDING",    (0,0),(-1,-1), 0),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                    ("VALIGN",        (0,0),(-1,-1), "TOP"),
                ]),
            )

            exec_outer = Table(
                [[grade_inner, badges_tbl]],
                colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45],
                style=TableStyle([
                    ("BACKGROUND",    (0,0),(-1,-1), c(_SURFACE)),
                    ("LEFTPADDING",   (0,0),(-1,-1), 16),
                    ("RIGHTPADDING",  (0,0),(-1,-1), 12),
                    ("TOPPADDING",    (0,0),(-1,-1), 16),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 16),
                    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                    ("ROUNDEDCORNERS", [6]),
                ]),
            )
            story.append(KeepTogether([exec_outer]))
            story.append(Spacer(1, 16))

        # ══════════════════════════════════════════════════════════════════
        # FINDINGS
        # ══════════════════════════════════════════════════════════════════
        if "findings" in sections and findings:
            story.append(Paragraph(
                "FINDINGS",
                sty("sec_hd2", fontSize=7, fontName="Helvetica-Bold",
                    textColor=c(_ACCENT), spaceAfter=6, tracking=1),
            ))

            col_widths = [0.85*inch, 1.1*inch, 2.3*inch, 2.25*inch]

            hdr_sty = sty("th", fontSize=8, fontName="Helvetica-Bold",
                           textColor=c(_TXT_SEC))
            cell_sty = sty("td", fontSize=8, textColor=c(_TXT_SEC), leading=11)

            rows: list = [[
                Paragraph("Severity",    hdr_sty),
                Paragraph("Category",    hdr_sty),
                Paragraph("Title",       hdr_sty),
                Paragraph("Remediation", hdr_sty),
            ]]

            style_cmds = [
                ("BACKGROUND",    (0, 0), (-1, 0),  c(_SURFACE)),
                ("LINEBELOW",     (0, 0), (-1, 0),  0.5, c(_ACCENT)),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
                ("TOPPADDING",    (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW",     (0, 1), (-1, -1), 0.3, c(_SURFACE2)),
            ]

            for i, f in enumerate(findings, start=1):
                sev      = (f.get("severity") or "info").lower()
                sev_col  = c(_SEV_COLOR.get(sev, _TXT_DIM))
                sev_bg   = c(_SEV_BG.get(sev, _SURFACE))
                row_bg   = c(_SURFACE) if i % 2 == 1 else c(_SURFACE2)

                sev_cell = Table(
                    [[Paragraph(sev.upper(),
                                sty(f"sv{i}", fontSize=7, fontName="Helvetica-Bold",
                                    textColor=sev_col, alignment=TA_CENTER))]],
                    colWidths=[0.7*inch],
                    style=TableStyle([
                        ("BACKGROUND",    (0,0),(-1,-1), sev_bg),
                        ("TOPPADDING",    (0,0),(-1,-1), 3),
                        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
                        ("LEFTPADDING",   (0,0),(-1,-1), 4),
                        ("RIGHTPADDING",  (0,0),(-1,-1), 4),
                        ("ROUNDEDCORNERS", [3]),
                    ]),
                )
                rows.append([
                    sev_cell,
                    Paragraph(str(f.get("category", ""))[:28], cell_sty),
                    Paragraph(str(f.get("title",    ""))[:90], cell_sty),
                    Paragraph(str(f.get("remediation", ""))[:140], cell_sty),
                ])
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), row_bg))

            tbl = Table(rows, colWidths=col_widths, repeatRows=1,
                        style=TableStyle(style_cmds))
            story.append(tbl)
            story.append(Spacer(1, 16))

        # ══════════════════════════════════════════════════════════════════
        # COMPLIANCE
        # ══════════════════════════════════════════════════════════════════
        if "compliance" in sections:
            story.append(Paragraph(
                "COMPLIANCE",
                sty("sec_hd3", fontSize=7, fontName="Helvetica-Bold",
                    textColor=c(_ACCENT), spaceAfter=6, tracking=1),
            ))

            compliance_refs: set[str] = set()
            for f in findings:
                for ref in (f.get("compliance") or []):
                    compliance_refs.add(ref)

            if compliance_refs:
                badge_data = [[
                    Paragraph(ref,
                              sty(f"cr{ref}", fontSize=8, fontName="Helvetica-Bold",
                                  textColor=c(_ACCENT_LT), alignment=TA_CENTER))
                    for ref in sorted(compliance_refs)
                ]]
                badge_w2 = CONTENT_W / max(len(compliance_refs), 1)
                comp_tbl = Table(
                    badge_data,
                    colWidths=[badge_w2] * len(compliance_refs),
                    style=TableStyle([
                        ("BACKGROUND",    (0,0),(-1,-1), c(_SURFACE2)),
                        ("LEFTPADDING",   (0,0),(-1,-1), 8),
                        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
                        ("TOPPADDING",    (0,0),(-1,-1), 10),
                        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
                        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
                        ("ROUNDEDCORNERS", [5]),
                    ]),
                )
                story.append(comp_tbl)
                story.append(Spacer(1, 6))
                story.append(Paragraph(
                    "This scan surfaces findings relevant to the compliance frameworks shown above.",
                    s_body,
                ))
            else:
                story.append(Paragraph(
                    "No specific compliance references detected in this scan. "
                    "Visit your HAWK dashboard Compliance page for HIPAA / FTC regulatory mapping.",
                    s_body,
                ))
            story.append(Spacer(1, 16))

        # ══════════════════════════════════════════════════════════════════
        # FOOTER
        # ══════════════════════════════════════════════════════════════════
        story.append(HR(width="100%", thickness=0.5, color=c(_SURFACE2),
                        spaceBefore=4, spaceAfter=6))
        story.append(Paragraph(
            f"Generated by <b>HAWK</b> — {BASE_URL} &nbsp;·&nbsp; {now_str}",
            sty("ft", fontSize=7, textColor=c(_TXT_DIM), alignment=TA_CENTER),
        ))

        doc.build(story)
        return output_path.exists()

    except Exception:
        return False
