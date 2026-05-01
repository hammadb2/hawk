"""Render the weekly threat briefing markdown body as a branded PDF.

Used by ``routers.portal_phase2.run_weekly_threat_briefings_for_all_clients``
to attach a polished PDF copy of each client's briefing to the Resend
delivery (priority list item #37). The HTML body in the email keeps the
text inline so customers can read it without opening an attachment, but
the PDF is what they save / forward to their compliance binder.

This is intentionally a small, dependency-light renderer: same reportlab
primitives + brand palette as ``services.report_pdf``, but only handles
the simple shape ``portal_ai.generate_weekly_threat_briefing_md`` emits
(``## title``, paragraphs, optional bullet list). No tables, no images,
no per-finding loops — keep the briefing scannable.

Returns ``bytes`` so the caller can base64 it directly into the Resend
``attachments`` payload without writing a temp file.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# Brand palette mirrors backend/services/report_pdf.py so attachments
# match the scan-report PDFs clients already receive.
_BG = "#07060C"
_SURFACE = "#0D0B14"
_ACCENT = "#7B5CF5"
_TXT = "#F2F0FA"
_TXT_SEC = "#9B98B4"
_TXT_DIM = "#5C5876"
_GREEN = "#00C48C"


def _normalize_company(company: str | None) -> str:
    return (company or "Your business").strip()[:120] or "Your business"


def _today_iso() -> str:
    return date.today().isoformat()


def _md_inline(text: str) -> str:
    """Convert ``**bold**`` and ``*italic*`` to reportlab Paragraph tags.

    HTML-escapes everything else so a stray ``<`` in the AI output can't
    blow up Paragraph parsing.
    """
    import html as _html

    safe = _html.escape(text, quote=False)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(r"(?<!\*)\*(?!\s)([^*]+?)\*", r"<i>\1</i>", safe)
    return safe


def render_weekly_briefing_pdf(
    *,
    company: str,
    title: str,
    body_md: str,
    industry: str | None = None,
    week_start: str | None = None,
) -> bytes:
    """Render the briefing as PDF bytes. Returns ``b''`` if reportlab missing.

    The empty-bytes fallback lets the email job degrade gracefully — it'll
    skip the attachment instead of failing the whole weekly cron.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
    except ImportError:
        logger.warning("reportlab not installed — skipping briefing PDF")
        return b""

    def c(hex_str: str) -> "colors.HexColor":
        return colors.HexColor(hex_str)

    company_clean = _normalize_company(company)
    week = week_start or _today_iso()
    industry_line = (industry or "Your sector").strip() or "Your sector"

    base_style = getSampleStyleSheet()["Normal"]

    def sty(name: str, **kw: Any) -> "ParagraphStyle":
        return ParagraphStyle(name, parent=base_style, **kw)

    s_h1 = sty(
        "h1",
        fontSize=20,
        fontName="Helvetica-Bold",
        textColor=c(_TXT),
        leading=24,
        spaceAfter=4,
    )
    s_h2 = sty(
        "h2",
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=c(_ACCENT),
        leading=18,
        spaceBefore=14,
        spaceAfter=6,
    )
    s_meta = sty(
        "meta",
        fontSize=9,
        textColor=c(_TXT_DIM),
        leading=12,
        spaceAfter=8,
    )
    s_body = sty(
        "body",
        fontSize=10.5,
        textColor=c(_TXT_SEC),
        leading=15.5,
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    s_bullet = sty(
        "bullet",
        fontSize=10.5,
        textColor=c(_TXT_SEC),
        leading=15,
        leftIndent=14,
        bulletIndent=2,
        spaceAfter=4,
    )
    s_footer = sty(
        "footer",
        fontSize=8,
        textColor=c(_TXT_DIM),
        leading=11,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.65 * inch,
        title=f"HAWK Weekly Threat Briefing — {company_clean}",
        author="HAWK Security",
    )

    story: list[Any] = []
    story.append(Paragraph("HAWK Weekly Threat Briefing", s_h1))
    story.append(
        Paragraph(
            f"{company_clean} &middot; {industry_line} &middot; Week of {week}",
            s_meta,
        )
    )
    story.append(HRFlowable(width="100%", thickness=0.6, color=c(_ACCENT), spaceAfter=10))

    if title and title.strip():
        story.append(Paragraph(_md_inline(title.strip()), s_h2))

    for raw in (body_md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            story.append(Spacer(1, 4))
            continue
        stripped = line.lstrip()
        if stripped.startswith("# "):
            story.append(Paragraph(_md_inline(stripped[2:].strip()), s_h1))
        elif stripped.startswith("## "):
            story.append(Paragraph(_md_inline(stripped[3:].strip()), s_h2))
        elif stripped.startswith("### "):
            story.append(Paragraph(_md_inline(stripped[4:].strip()), s_h2))
        elif stripped.startswith(("- ", "* ")):
            story.append(
                Paragraph(_md_inline(stripped[2:].strip()), s_bullet, bulletText="•")
            )
        else:
            story.append(Paragraph(_md_inline(stripped), s_body))

    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.4, color=c(_TXT_DIM)))
    story.append(Spacer(1, 6))
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y")
    story.append(
        Paragraph(
            f"Prepared by HAWK Security &middot; Generated {generated} UTC &middot; "
            f"securedbyhawk.com",
            s_footer,
        )
    )

    try:
        doc.build(story)
    except Exception:
        logger.exception("reportlab failed to build briefing PDF")
        return b""
    return buf.getvalue()


def briefing_filename(*, company: str, week_start: str | None = None) -> str:
    """Deterministic, filesystem-safe filename for the attached PDF."""
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", _normalize_company(company)).strip("-")
    week = week_start or _today_iso()
    return f"hawk-weekly-threat-briefing-{safe}-{week}.pdf"
